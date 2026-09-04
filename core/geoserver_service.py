import re
import unicodedata

import requests

from .http_lock import HTTP_SESSION_LOCK

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def parse_postgres_uri(source):
    """Extrai host/port/dbname/user/schema/table de layer.source() de uma camada PostGIS
    do QGIS. Compartilhado entre GeoServerService (publicação) e PersistenceService
    (salvar/ler metadado no banco) — mesmo formato de URI, uma cópia só do regex."""
    details = {}
    pattern = re.compile(r"(\w+)='([^']*)'|(\w+)=([^\s]+)")
    matches = pattern.findall(source or '')

    for key_quoted, val_quoted, key_unquoted, val_unquoted in matches:
        key = key_quoted or key_unquoted
        value = val_quoted or val_unquoted
        if key:
            details[key] = value

    details['f_table_catalog'] = details.get('dbname')
    full_table_identifier = details.get('table', '')
    clean_identifier = full_table_identifier.replace('"', '')

    if '.' in clean_identifier:
        parts = clean_identifier.split('.', 1)
        details['f_table_schema'] = parts[0]
        details['f_table_name'] = parts[1]
    else:
        details['f_table_schema'] = details.get('sschema', details.get('schema', 'public'))
        details['f_table_name'] = clean_identifier

    return details


def resolve_layer_db_params(layer):
    """Resolve os parâmetros de conexão (dict puro, sem I/O de rede ainda) e os detalhes
    da tabela pra essa camada PostGIS - extraído de connect_to_layer_db pra poder rodar em
    background (QThread, ver _GsActiveLayerInfoWorker/geoserver_workers.py): só ESSA parte
    (layer.source(), QgsApplication.authManager()) toca API do QGIS, que só pode ser usada
    na main thread. O psycopg2.connect() em si (rede) não - por isso fica separado, pra
    quem quiser rodar a conexão de verdade em background só precisar chamar essa função
    antes (na main thread) e levar o dict resultante pro worker."""
    details = parse_postgres_uri(layer.source())
    db_user = details.get('user')
    db_password = details.get('password')

    if not db_password and details.get('authcfg'):
        from qgis.core import QgsApplication
        auth_manager = QgsApplication.authManager()
        auth_cfg_id = details['authcfg']
        config = auth_manager.availableAuthMethodConfigs().get(auth_cfg_id)
        if config and auth_manager.loadAuthenticationConfig(auth_cfg_id, config, True):
            db_user = config.configMap().get('username')
            db_password = config.configMap().get('password')
        else:
            raise Exception(f"Não foi possível carregar a configuração de autenticação '{auth_cfg_id}'.")

    params = {
        'dbname': details.get('dbname'),
        'user': db_user,
        'password': db_password,
        'host': details.get('host'),
        'port': details.get('port', 5432),
    }
    return params, details


def connect_to_layer_db(layer):
    """Abre uma conexão psycopg2 direta com o banco da própria camada PostGIS (mesma
    lógica de auth de core/persistence_service.py's _save_to_db/_load_from_db, mas
    extraída aqui pra não duplicar uma terceira vez em save_publish_destination/
    load_publish_destination abaixo - não mexe no persistence_service.py existente pra
    não arriscar o caminho de salvar metadado, que já funciona em produção). Não precisa
    de login no GeoServer/GeoNetwork - só a credencial da camada já configurada no QGIS."""
    if not psycopg2:
        raise Exception("A biblioteca psycopg2 não foi encontrada.")
    params, details = resolve_layer_db_params(layer)
    return psycopg2.connect(**params), details


class GeoServerService:
    """
    Serviço que abstrai a comunicação com o GeoServer (API REST). Espelha o padrão
    de core/geonetwork_service.py - nenhuma dependência de Qt aqui, só requests puro.
    """
    def __init__(self, plugin):
        self.plugin = plugin

    def _get_rest_session(self):
        """Retorna a sessão correta para chamadas REST do GeoServer:
        - gs_rest_session (credenciais admin Basic Auth): usada quando o usuário SSO
          não consegue autenticar via Bearer token no GeoServer REST (AADSTS650057).
        - api_session: fallback quando gs_rest_session não está configurada (admin local
          funciona direto com Basic Auth via api_session).
        Se nenhuma estiver disponível, levanta Exception."""
        gs = getattr(self.plugin, 'gs_rest_session', None)
        if gs:
            return gs
        api = getattr(self.plugin, 'api_session', None)
        if api:
            return api
        raise Exception("Sessão não foi inicializada. Faça login primeiro.")

    def list_workspaces(self, config_loader_instance):
        """RF01 - lista os workspaces disponíveis no GeoServer."""
        api_session = self._get_rest_session()

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        with HTTP_SESSION_LOCK:
            response = api_session.get(
                f"{base_url}/rest/workspaces",
                headers={'Accept': 'application/json'},
                timeout=15,
                verify=False
            )
        response.raise_for_status()
        data = response.json()
        workspaces = (data.get('workspaces') or {}).get('workspace') or []
        if isinstance(workspaces, dict):
            workspaces = [workspaces]
        return [w.get('name') for w in workspaces if w.get('name')]

    def list_datastores(self, workspace, config_loader_instance):
        """RF01 - lista os datastores de um workspace do GeoServer."""
        api_session = self._get_rest_session()

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        with HTTP_SESSION_LOCK:
            response = api_session.get(
                f"{base_url}/rest/workspaces/{workspace}/datastores",
                headers={'Accept': 'application/json'},
                timeout=15,
                verify=False
            )
        response.raise_for_status()
        data = response.json()
        datastores = (data.get('dataStores') or {}).get('dataStore') or []
        if isinstance(datastores, dict):
            datastores = [datastores]
        return [d.get('name') for d in datastores if d.get('name')]

    def list_featuretypes(self, workspace, datastore, config_loader_instance):
        """Lista as tabelas visíveis nesse datastore (list=all - inclui as ainda não
        publicadas), igual a tela 'Publicar'/'Publicar novamente' do próprio GeoServer.
        Usado pra confirmar, ANTES do usuário clicar em publicar, que a tabela da camada
        ativa do QGIS realmente existe nesse workspace/datastore - evita o 400 'no
        attributes were specified' que acontece quando o Schema configurado no datastore
        é diferente do schema onde a tabela vive de verdade no banco."""
        api_session = self._get_rest_session()

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        with HTTP_SESSION_LOCK:
            response = api_session.get(
                f"{base_url}/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes",
                params={'list': 'all'},
                headers={'Accept': 'application/json'},
                timeout=20,
                verify=False
            )
        response.raise_for_status()
        data = response.json()
        names = (data.get('list') or {}).get('string') or []
        if isinstance(names, str):
            names = [names]  # GeoServer devolve string solta (não array) quando só tem 1 item
        return names

    def list_published_featuretypes(self, workspace, datastore, config_loader_instance):
        """Lista só as camadas JÁ PUBLICADAS nesse workspace/datastore (sem `list=all` - ao
        contrário de list_featuretypes, que também inclui tabelas nunca publicadas, pensado
        pra validar ANTES de publicar). Usado pelo seletor "Selecionar camada publicada"
        (aba Destino) pra filtrar a lista quando o usuário já escolheu Workspace/Datastore -
        pedido do usuário: sem isso a lista mostra TODAS as camadas do GeoServer inteiro
        (via WMS, ver GeoServerBridge.search_geoserver), mesmo as de outros datastores."""
        api_session = self._get_rest_session()

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        with HTTP_SESSION_LOCK:
            response = api_session.get(
                f"{base_url}/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes.json",
                headers={'Accept': 'application/json'},
                timeout=20,
                verify=False
            )
        response.raise_for_status()
        data = response.json()
        entries = (data.get('featureTypes') or {}).get('featureType') or []
        if isinstance(entries, dict):
            entries = [entries]
        return [e.get('name') for e in entries if e.get('name')]

    def find_datastore_for_table(self, table_name, config_loader_instance, progress_callback=None):
        """Varre todos os workspaces/datastores do GeoServer procurando onde a tabela
        `table_name` está visível (list=all) - usado pelo botão "Detectar automaticamente"
        quando o usuário não sabe o workspace/datastore certo da camada. Pode demorar (1
        chamada REST por workspace + 1 por datastore de cada workspace), por isso reporta
        progresso via `progress_callback(mensagem)` quando fornecido. Retorna uma lista de
        {'workspace':..., 'datastore':...} - pode ter mais de um resultado se a tabela
        aparecer em mais de um datastore."""
        workspaces = self.list_workspaces(config_loader_instance)
        matches = []
        table_lower = (table_name or '').lower()
        for i, ws in enumerate(workspaces):
            if progress_callback:
                progress_callback(f'Verificando workspace "{ws}" ({i + 1}/{len(workspaces)})...')
            try:
                datastores = self.list_datastores(ws, config_loader_instance)
            except Exception:
                continue
            for ds in datastores:
                try:
                    names = self.list_featuretypes(ws, ds, config_loader_instance)
                except Exception:
                    continue
                if any((n or '').lower() == table_lower for n in names):
                    matches.append({'workspace': ws, 'datastore': ds})
        return matches

    def find_datastore_for_published_name(self, workspace, published_name, config_loader_instance,
                                          progress_callback=None):
        """Dado um workspace e um published_name (ex.: do link WMS/WFS de um metadado GN),
        descobre em qual datastore esse FeatureType está publicado.

        Diferente de find_datastore_for_table (que busca pelo nome da TABELA via list=all),
        este tenta fetch_published_featuretype em cada datastore do workspace — mais preciso
        quando só temos o nome publicado (sem acesso à camada PostGIS local). Retorna o nome
        do primeiro datastore que responder 200 (não None), ou None se não encontrar em nenhum.

        Usado por pull_gs_layer_by_wms_name para completar a tripla workspace/datastore/name
        necessária para _GsPullLayerWorker, partindo apenas de workspace:published_name como
        vem do CI_OnlineResource name do metadado GN (xml_parser.py, wms_data.geoserver_layer_name)."""
        try:
            datastores = self.list_datastores(workspace, config_loader_instance)
        except Exception as e:
            raise Exception(f'Não foi possível listar datastores do workspace "{workspace}": {e}')

        for i, ds in enumerate(datastores):
            if progress_callback:
                progress_callback(f'Procurando em "{workspace}/{ds}" ({i + 1}/{len(datastores)})...')
            try:
                result = self.fetch_published_featuretype(workspace, ds, published_name, config_loader_instance)
                if result is not None:  # 200 OK — found it
                    return ds
            except Exception:
                continue  # 404 ou erro de rede — tenta o próximo datastore
        return None


    @staticmethod
    def sanitize_layer_name(name):
        """RF04 - regex obrigatório `[a-z][a-z0-9_]*`: minúsculas, sem espaços/acentos/
        caracteres especiais, e nunca começando com número (bug conhecido do GeoServer)."""
        normalized = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode('ascii')
        clean = re.sub(r'[^a-z0-9_]', '_', normalized.lower())
        clean = re.sub(r'_+', '_', clean).strip('_')
        if not clean:
            clean = 'camada'
        if clean[0].isdigit():
            clean = 'l_' + clean
        return clean

    @staticmethod
    def get_active_layer_publish_info(layer):
        """Decide se `layer` (QgsMapLayer ou None) pode ser publicada no GeoServer.
        Regra de negócio: só camadas que já vivem no banco PostgreSQL podem ser publicadas
        (RF02) - upload de arquivo local não é suportado, ver requisitos_v2.md."""
        if not layer:
            return {'publishable': False, 'reason': 'Nenhuma camada ativa no QGIS.'}

        if layer.providerType() != 'postgres':
            return {
                'publishable': False,
                'name': layer.name(),
                'reason': (
                    'Publicação só é suportada para camadas do banco PostgreSQL. '
                    'Salve esta camada no banco antes de publicar no GeoServer.'
                ),
            }

        details = parse_postgres_uri(layer.source())
        table = details.get('f_table_name')
        schema = details.get('f_table_schema') or 'public'
        if not table:
            return {
                'publishable': False,
                'name': layer.name(),
                'reason': 'Não foi possível identificar a tabela desta camada no banco.',
            }

        return {
            'publishable': True,
            'name': layer.name(),
            'schema': schema,
            'table': table,
        }

    def register_postgis_featuretype(self, workspace, datastore, native_table_name, published_name,
                                      config_loader_instance, title=None, abstract=None, keywords=None, srs=None,
                                      metadata_link_url=None):
        """RF02 - registro lógico: expõe uma tabela PostGIS já existente num datastore do
        GeoServer como FeatureType, sem tráfego de dados espaciais. 'name'/'nativeName'
        seguem a sanitização RF04; 'title' é livre (sem essas regras); 'abstract' e
        'keywords', quando fornecidos, vêm do metadado MGB já salvo pra camada.
        `metadata_link_url`, quando fornecido, vira um "Link de metadados" (aba
        Identificação da camada na UI do GeoServer) apontando pro registro MGB no
        GeoNetwork - só setado quando a camada JÁ tem um metadata_uuid salvo de verdade
        (ver GeoServerBridge.publish_layer), nunca um rascunho não publicado (linkaria pra
        um registro que ainda não existe no catálogo).

        `srs` foi uma tentativa de mandar explicitamente nativeCRS/srs/projectionPolicy
        (CRS que o QGIS já conhece da camada) pra evitar "SRS Nativo" vazio na UI do
        GeoServer - REVERTIDA: causou [GS-500] na publicação (forçar nativeCRS na criação
        via JSON é uma área conhecida por dar erro 500 no binding JSON do GeoServer -
        provavelmente precisa ser feito via XML, ou só depois via PUT de atualização, não
        no POST de criação). Parâmetro mantido (não usado) só pra não quebrar a assinatura
        de quem já chama passando `srs=` - não fazer nada com ele até ter um jeito
        confirmado de não derrubar a publicação."""
        api_session = self._get_rest_session()

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        payload = {
            'featureType': {
                'name': published_name,
                'nativeName': native_table_name,
                'title': title or published_name,
            }
        }
        if abstract:
            payload['featureType']['abstract'] = abstract
        if keywords:
            payload['featureType']['keywords'] = {'string': list(keywords)}
        if metadata_link_url:
            # metadataType 'TC211' (não 'ISO19115:2003') de propósito - é o valor que o
            # próprio GeoServer reconhece pra expor o link no GetCapabilities do WMS 1.1.1
            # (aviso "Note only FGDC and TC211 metadata links show up in WMS 1.1.1
            # capabilities", visível na tela "Adicionar link" do GeoServer) - com
            # 'ISO19115:2003' o link é salvo mas fica invisível pra esse propósito.
            # type 'application/xml' (não 'text/xml') porque é o Content-Type de verdade
            # que .../formatters/xml (GeoNetwork) devolve nessa URL.
            payload['featureType']['metadataLinks'] = {
                'metadataLink': [
                    {'type': 'application/xml', 'metadataType': 'TC211', 'content': metadata_link_url}
                ]
            }

        with HTTP_SESSION_LOCK:
            response = api_session.post(
                f"{base_url}/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes",
                json=payload,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                timeout=30,
                verify=False
            )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise Exception(self.translate_gs_error(response.status_code, response.text or ''))

    def update_published_featuretype(self, workspace, datastore, published_name, config_loader_instance,
                                     title=None, abstract=None, keywords=None, metadata_link_url=None):
        """Atualiza Título, Resumo, Palavras-chave e Link de Metadados de uma camada já publicada
        (FeatureType) via PUT, sem precisar da camada PostGIS física. Ideal para sincronização de
        metadados (fluxo sem camada QGIS ativa, ver GeoServerBridge.update_layer_metadata).

        `metadata_link_url` segue exatamente o mesmo formato de register_postgis_featuretype
        (metadataType 'TC211'/type 'application/xml' - é o valor que o GeoServer reconhece pra
        expor o link no GetCapabilities do WMS 1.1.1, ver comentário lá) - os dois precisam
        concordar, senão esse fluxo alternativo publicaria um link num formato diferente do da
        publicação normal."""
        api_session = self._get_rest_session()
        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        payload = {'featureType': {'name': published_name}}
        if title is not None:
            payload['featureType']['title'] = title
        if abstract is not None:
            payload['featureType']['abstract'] = abstract
        if keywords is not None:
            payload['featureType']['keywords'] = {'string': [k.strip() for k in keywords if k.strip()]}
        if metadata_link_url:
            payload['featureType']['metadataLinks'] = {
                'metadataLink': [
                    {'type': 'application/xml', 'metadataType': 'TC211', 'content': metadata_link_url}
                ]
            }

        import json
        with HTTP_SESSION_LOCK:
            response = api_session.put(
                f"{base_url}/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes/{published_name}.json",
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                data=json.dumps(payload),
                timeout=30,
                verify=False
            )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise Exception(self.translate_gs_error(response.status_code, response.text or ''))


    def fetch_published_featuretype(self, workspace, datastore, published_name, config_loader_instance):
        """Busca o featuretype de VERDADE no GeoServer (REST, ao vivo) - é a fonte mais
        confiável de 'o que está publicado agora', ao contrário do banco
        (geoserver_publish_xml), que só guarda o que foi usado na ÚLTIMA publicação/
        salvamento e pode divergir se o título/resumo foi editado e só salvo no banco
        ("Continuar Depois") sem republicar de verdade (ver GeoServerBridge.check_gs_sync,
        que usa isso pro nível 'sistema' do badge - mesmo espírito de
        GeoNetworkService.fetch_from_geonetwork pro lado GN). Retorna None se o
        featuretype não existir nesse workspace/datastore (nunca publicado de verdade, ou
        removido de lá)."""
        api_session = self._get_rest_session()

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        with HTTP_SESSION_LOCK:
            response = api_session.get(
                f"{base_url}/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes/{published_name}.json",
                headers={'Accept': 'application/json'},
                timeout=15,
                verify=False
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        ft = data.get('featureType') or {}
        keywords_raw = (ft.get('keywords') or {}).get('string') or []
        if isinstance(keywords_raw, str):
            keywords_raw = [keywords_raw]  # GeoServer devolve string solta (não array) quando só tem 1 item
        return {
            'title': ft.get('title') or '',
            'abstract': ft.get('abstract') or '',
            'keywords': keywords_raw,
            # uuid do metadado GN de fato vinculado a ESSA camada no GeoServer agora (não
            # um palpite vindo de estado de sessão solto tipo _gnSyncUuid, JS) - extraído
            # do próprio metadataLinks que register_postgis_featuretype/
            # update_published_featuretype gravaram na publicação (formato
            # "{records_url}/{uuid}/formatters/xml", ver _build_metadata_link_url,
            # geoserver_bridge.py). Fonte confiável pro fallback "sem camada ativa" (Bug 57)
            # - o pull TRAZ o uuid real vinculado, em vez de depender de o usuário ter
            # acabado de puxar o MESMO registro no editor GN nesta sessão.
            'metadata_uuid': self._extract_metadata_uuid(ft),
        }

    @staticmethod
    def _extract_metadata_uuid(feature_type):
        """Extrai o uuid do primeiro metadataLink de um featureType (resposta REST do
        GeoServer) - reverso de _build_metadata_link_url (geoserver_bridge.py):
        "{records_url}/{uuid}/formatters/xml" -> uuid. Vazio se não houver link nenhum, ou
        se o formato não bater (link de metadados manual, formato antigo, etc.)."""
        links = ((feature_type or {}).get('metadataLinks') or {}).get('metadataLink') or []
        if isinstance(links, dict):
            links = [links]
        for link in links:
            content = (link or {}).get('content') or ''
            match = re.search(r'/([0-9a-fA-F-]{36})/formatters/xml/?$', content)
            if match:
                return match.group(1)
        return ''

    # ── Estilos (SLD) ───────────────────────────────────────────────────────────

    def list_styles(self, workspace, config_loader_instance):
        """Lista os estilos disponíveis pra associar a uma camada: os GLOBAIS
        (/rest/styles) + os do workspace de publicação (/rest/workspaces/{ws}/styles),
        já que os dois escopos podem ser usados como estilo padrão de uma camada desse
        workspace. Retorna [{'name':..., 'workspace': ''|ws}] - workspace vazio = global."""
        api_session = self._get_rest_session()

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        styles = []

        def _collect(url, ws_label):
            with HTTP_SESSION_LOCK:
                response = api_session.get(url, headers={'Accept': 'application/json'}, timeout=15, verify=False)
            if response.status_code == 404:
                return  # workspace sem estilos próprios ainda - não é erro
            response.raise_for_status()
            data = response.json()
            entries = data.get('styles')
            # GeoServer devolve {"styles": ""} quando a lista está vazia (não um dict)
            entries = entries.get('style') if isinstance(entries, dict) else None
            if isinstance(entries, dict):
                entries = [entries]  # e um objeto solto (não array) quando só tem 1 item
            for s in (entries or []):
                if s.get('name'):
                    styles.append({'name': s['name'], 'workspace': ws_label})

        _collect(f"{base_url}/rest/styles", '')
        if workspace:
            _collect(f"{base_url}/rest/workspaces/{workspace}/styles", workspace)
        return styles

    def style_exists(self, workspace, style_name, config_loader_instance):
        """True se o estilo já existe (escopo do workspace quando `workspace` não-vazio,
        global caso contrário) - decide entre POST (criar) e PUT (atualizar) no upload_sld."""
        api_session = self._get_rest_session()
        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        scope = f"workspaces/{workspace}/" if workspace else ''
        with HTTP_SESSION_LOCK:
            response = api_session.get(
                f"{base_url}/rest/{scope}styles/{style_name}.json",
                headers={'Accept': 'application/json'},
                timeout=15,
                verify=False
            )
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    @staticmethod
    def _sld_content_type(sld_body):
        """O GeoServer exige Content-Type diferente por versão do SLD: 1.0.0 =
        application/vnd.ogc.sld+xml, 1.1.0 (o que o QGIS exporta via saveSldStyle) =
        application/vnd.ogc.se+xml - mandar o tipo errado dá 400 'Unable to parse'."""
        if 'version="1.1.0"' in (sld_body or '') or "version='1.1.0'" in (sld_body or ''):
            return 'application/vnd.ogc.se+xml'
        return 'application/vnd.ogc.sld+xml'

    def upload_sld(self, workspace, style_name, sld_body, config_loader_instance):
        """Cria (POST) ou atualiza (PUT) um estilo SLD no escopo do workspace. O corpo é
        o XML SLD cru - o GeoServer valida na hora e responde 400 com a causa quando o
        SLD é inválido (ex.: simbologia QGIS sem equivalente SLD)."""
        api_session = self._get_rest_session()

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        headers = {'Content-Type': self._sld_content_type(sld_body)}
        body = (sld_body or '').encode('utf-8')
        if self.style_exists(workspace, style_name, config_loader_instance):
            with HTTP_SESSION_LOCK:
                response = api_session.put(
                    f"{base_url}/rest/workspaces/{workspace}/styles/{style_name}",
                    data=body, headers=headers, timeout=30, verify=False
                )
        else:
            with HTTP_SESSION_LOCK:
                response = api_session.post(
                    f"{base_url}/rest/workspaces/{workspace}/styles",
                    params={'name': style_name},
                    data=body, headers=headers, timeout=30, verify=False
                )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise Exception(self.translate_gs_error(response.status_code, response.text or ''))

    @staticmethod
    def _split_style_ref(name, workspace=''):
        """Normaliza uma referência de estilo vinda do GeoServer: o JSON de /rest/layers
        pode trazer o nome já prefixado ('ws:nome') E AINDA ASSIM trazer a chave
        'workspace' separada preenchida (dependendo da versão) - por isso sempre tira o
        prefixo do nome quando presente, independente de já ter vindo um workspace
        separado. Sem isso, os dois se somavam e o prefixo dobrava ('ws:ws:nome') no
        nome exibido pra estilos adicionais depois de 'Baixar Camada'. Retorna
        (nome_puro, workspace)."""
        name = name or ''
        if ':' in name:
            split_ws, name = name.split(':', 1)
            workspace = workspace or split_ws
        return name, (workspace or '')

    def fetch_layer_styles(self, layer_workspace, published_name, config_loader_instance):
        """Busca o estilo PADRÃO e os ADICIONAIS da camada AO VIVO
        (GET /rest/layers/{ws}:{nome}.json) - complementa fetch_published_featuretype,
        que não sabe nada de estilo. Usado pelo nível 'sistema' do badge
        (_GsSyncCheckWorker). Retorna {'default_style': nome, 'default_style_workspace':
        ws, 'additional': ['ws:nome'|'nome', ...]} ou None se a camada não existir."""
        api_session = self._get_rest_session()

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        with HTTP_SESSION_LOCK:
            response = api_session.get(
                f"{base_url}/rest/layers/{layer_workspace}:{published_name}.json",
                headers={'Accept': 'application/json'},
                timeout=15,
                verify=False
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        layer = (response.json() or {}).get('layer') or {}
        default = layer.get('defaultStyle') or {}
        d_name, d_ws = self._split_style_ref(default.get('name'), default.get('workspace'))
        styles = layer.get('styles') or {}
        entries = styles.get('style') if isinstance(styles, dict) else None
        if isinstance(entries, dict):
            entries = [entries]  # objeto solto (não array) quando só tem 1 item
        additional = []
        for s in (entries or []):
            s_name, s_ws = self._split_style_ref(s.get('name'), s.get('workspace'))
            if s_name:
                additional.append({'name': s_name, 'style_workspace': s_ws})
        return {'default_style': d_name, 'default_style_workspace': d_ws, 'additional': additional}

    def apply_style(self, layer_workspace, published_name, style_task, config_loader_instance):
        """Executa a tarefa de estilo montada pelo bridge (_prepare_style_task):
        `style_task` = {'default': {...}|None, 'additional': [{...}, ...]}. Sobe os SLDs
        que têm corpo (gerados do QGIS/lidos de arquivo) e atualiza a camada num PUT
        único (defaultStyle + lista styles). Lista de adicionais VAZIA não toca nos
        adicionais que já existem no GeoServer (o PUT com 'styles' SUBSTITUI a lista
        inteira - mandar [] apagaria adicionais configurados por fora do plugin).
        Chamado pelos workers (_GsPublishWorker/_GsUpdateMetadataWorker) - nunca na UI
        thread (RNF02)."""
        if not style_task:
            return
        api_session = self._get_rest_session()

        default = style_task.get('default')
        additional = style_task.get('additional') or []

        for entry in ([default] if default else []) + additional:
            if entry.get('sld_body'):
                self.upload_sld(entry['style_workspace'], entry['name'],
                                entry['sld_body'], config_loader_instance)

        def _style_ref(entry):
            ref = {'name': entry['name']}
            if entry.get('style_workspace'):
                ref['workspace'] = entry['style_workspace']
            return ref

        layer_payload = {}
        if default:
            layer_payload['defaultStyle'] = _style_ref(default)
        if additional:
            style_list = [_style_ref(e) for e in additional]
            layer_payload['styles'] = {
                'style': style_list if len(style_list) > 1 else style_list[0]
            }
        if not layer_payload:
            return

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        with HTTP_SESSION_LOCK:
            response = api_session.put(
                f"{base_url}/rest/layers/{layer_workspace}:{published_name}.json",
                json={'layer': layer_payload},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                timeout=30,
                verify=False
            )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise Exception(self.translate_gs_error(response.status_code, response.text or ''))

    @staticmethod
    def _build_publish_xml(workspace, datastore, published_name, title, abstract=None, keywords=None, published=False,
                           style_source='', style_name='', style_workspace='', style_additional_json=''):
        import xml.etree.ElementTree as ET
        root = ET.Element('geoserver_publish')
        ET.SubElement(root, 'workspace').text = workspace or ''
        ET.SubElement(root, 'datastore').text = datastore or ''
        ET.SubElement(root, 'published_name').text = published_name or ''
        ET.SubElement(root, 'title').text = title or ''
        ET.SubElement(root, 'abstract').text = abstract or ''
        keywords_el = ET.SubElement(root, 'keywords')
        for kw in (keywords or []):
            ET.SubElement(keywords_el, 'keyword').text = kw
        # Distingue "só salvo" (Continuar Depois - GeoServer não sabe disso ainda) de
        # "publicado de verdade" (registro lógico confirmado na REST API) - sem isso o
        # badge do JS não teria como diferenciar "Salvo" de "Sincronizado/Publicado".
        ET.SubElement(root, 'published').text = 'true' if published else 'false'
        # Estilo (SLD) usado na última publicação/salvamento: source = 'qgis'|'file'|
        # 'existing' ('' = nunca definiu estilo pelo plugin - registros antigos caem aqui
        # via _parse_publish_xml, que devolve '' pra tag ausente).
        ET.SubElement(root, 'style_source').text = style_source or ''
        ET.SubElement(root, 'style_name').text = style_name or ''
        ET.SubElement(root, 'style_workspace').text = style_workspace or ''
        ET.SubElement(root, 'style_additional_json').text = style_additional_json or ''
        body = ET.tostring(root, encoding='unicode')
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + body

    @staticmethod
    def _parse_publish_xml(xml_text):
        import xml.etree.ElementTree as ET
        if not xml_text:
            return None
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None
        get = lambda tag: (root.findtext(tag) or '')
        keywords_el = root.find('keywords')
        keywords = [k.text for k in keywords_el.findall('keyword') if k.text] if keywords_el is not None else []
        return {
            'workspace': get('workspace'),
            'datastore': get('datastore'),
            'published_name': get('published_name'),
            'title': get('title'),
            'abstract': get('abstract'),
            'keywords': keywords,
            'published': get('published') == 'true',
            'style_source': get('style_source'),
            'style_name': get('style_name'),
            'style_workspace': get('style_workspace'),
            'style_additional_json': get('style_additional_json'),
        }

    @staticmethod
    def save_publish_destination(layer, workspace, datastore, published_name, title, abstract=None, keywords=None, published=False,
                                 style_source='', style_name='', style_workspace='', style_additional_json=''):
        """Guarda no banco da própria camada, na mesma linha/tabela do metadado
        (public.qgis_geometadata_plugin, coluna geoserver_publish_xml) qual workspace/
        datastore/nome/título/resumo/palavras-chave foram usados na última publicação -
        pra pré-preencher a aba Destino/Identificação da próxima vez, mesmo sem rascunho
        local. Chamado automaticamente logo após uma publicação bem-sucedida (ver
        GeoServerBridge._on_publish_done) e também ao promover um rascunho local via
        "Continuar Depois" (ver GeoMetadata_dialog._promote_gs_draft_to_db). O UPSERT toca
        só essa coluna - nunca mexe em metadata_xml/owner/update_time, que são exclusivos
        do fluxo "Continuar Depois" do editor GN (core/persistence_service.py); os dois
        lados fazem UPSERTs independentes na mesma linha sem pisar um no outro, o Postgres
        só sobrescreve a coluna listada no SET. Falha silenciosa se a coluna/tabela ainda
        não existir nesse banco (mesma condição do Bug 1 documentado em docs_projeto/
        bugs.md) - é só bookkeeping, não pode derrubar uma publicação que já deu certo.
        Retorna True/False (não levanta exceção) - o botão "Continuar Depois" do painel
        GeoServer usa isso pra avisar o usuário se a gravação no banco realmente aconteceu.

        `published`: True só quando essa gravação corresponde a uma publicação de verdade
        na REST API do GeoServer (chamado por _on_publish_done); False pros demais
        caminhos ("Continuar Depois", promoção de rascunho) - o registro fica salvo no
        banco, mas o GeoServer ainda NÃO tem essa informação. O JS usa essa flag pra
        diferenciar o badge "Salvo (não publicado)" de "Sincronizado" (ver geoserver.js,
        _checkGsSyncNow) - evita o usuário achar que salvar no banco equivale a publicar."""
        if not psycopg2 or not layer:
            return False
        try:
            conn, details = connect_to_layer_db(layer)
        except Exception as exc:
            print(f"GeoMetadata [save_publish_destination] conexão: {exc}")
            return False
        try:
            cursor = conn.cursor()
            xml_text = GeoServerService._build_publish_xml(workspace, datastore, published_name, title, abstract, keywords, published,
                                                           style_source, style_name, style_workspace, style_additional_json)
            sql = """
                INSERT INTO public.qgis_geometadata_plugin
                    (f_table_catalog, f_table_schema, f_table_name, geoserver_publish_xml)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT qgis_geometadata_plugin_unique_layer
                DO UPDATE SET geoserver_publish_xml = EXCLUDED.geoserver_publish_xml;
            """
            cursor.execute(sql, (
                details.get('f_table_catalog'), details['f_table_schema'], details['f_table_name'], xml_text
            ))
            conn.commit()
            cursor.close()
            return True
        except psycopg2.errors.UndefinedColumn:
            return False  # coluna ainda não provisionada nesse banco - condição conhecida, sem traceback
        except Exception as exc:
            print(f"GeoMetadata [save_publish_destination]: {exc}")
            return False
        finally:
            conn.close()

    @staticmethod
    def fetch_saved_records(conn_params, f_table_catalog, f_table_schema, f_table_name):
        """Busca de uma vez só (UMA conexão) o metadado MGB salvo (metadata_xml) e o
        destino de publicação salvo (geoserver_publish_xml) - as duas colunas vivem na
        MESMA linha da MESMA tabela (public.qgis_geometadata_plugin); antes eram duas
        conexões psycopg2 separadas (get_active_layer_publish_info abria uma pra cada),
        dobrando à toa o custo de rede. Recebe os parâmetros de conexão já resolvidos
        (ver resolve_layer_db_params) - thread-safe, pra rodar em background (QThread,
        RNF02 - ver _GsActiveLayerInfoWorker/geoserver_workers.py): psycopg2.connect()
        bloqueava a thread principal do Qt (inclusive o compositor da QWebEngineView, que
        reusa o mesmo event loop) toda vez que o painel GS abria ou a camada ativa mudava,
        sem short-circuit nenhum (diferente do editor GN, que só cai pro banco quando não
        há rascunho local - ver geonetwork_bridge.load_draft).

        As duas colunas são checadas em SELECTs separados (mesmo `cursor`/conexão) em vez
        de um só com as duas - um banco só com uma das colunas provisionada (migração
        parcial) faria o SELECT combinado falhar inteiro, perdendo a coluna que EXISTE
        junto com a que não existe. Retorna (local_metadata: dict|None, saved_destination:
        dict|None).

        A conexão em si (psycopg2.connect) não é protegida por try/except aqui de
        propósito - deixa psycopg2.OperationalError (banco inacessível: host fora do ar,
        rede/VPN caída, etc.) propagar pro chamador (_GsActiveLayerInfoWorker.run()), que
        já roda isso dentro do próprio try/except e sabe avisar o usuário. Engolir e
        devolver (None, None) aqui era indistinguível de "nada salvo ainda" - causa raiz
        de vários bugs de badge quando o Postgres estava fora do ar (docs_projeto/bugs.md)."""
        if not psycopg2:
            return None, None
        conn = psycopg2.connect(**conn_params)
        local_metadata, saved_destination = None, None
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT metadata_xml FROM public.qgis_geometadata_plugin "
                    "WHERE f_table_catalog = %s AND f_table_schema = %s AND f_table_name = %s;",
                    (f_table_catalog, f_table_schema, f_table_name)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    from . import xml_parser
                    local_metadata = xml_parser.parse_xml_to_dict(row[0], is_string=True)
            except psycopg2.errors.UndefinedColumn:
                # rollback obrigatório - sem isso a transação fica "abortada" e o segundo
                # SELECT (geoserver_publish_xml) falha em cadeia mesmo que a coluna DELE exista.
                conn.rollback()

            try:
                cursor.execute(
                    "SELECT geoserver_publish_xml FROM public.qgis_geometadata_plugin "
                    "WHERE f_table_catalog = %s AND f_table_schema = %s AND f_table_name = %s;",
                    (f_table_catalog, f_table_schema, f_table_name)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    saved_destination = GeoServerService._parse_publish_xml(row[0])
            except psycopg2.errors.UndefinedColumn:
                conn.rollback()
            cursor.close()
        except Exception as exc:
            print(f"GeoMetadata [fetch_saved_records]: {exc}")
        finally:
            conn.close()
        return local_metadata, saved_destination

    @staticmethod
    def translate_gs_error(status_code, text):
        """Traduz erros comuns da REST API do GeoServer (RN02)."""
        lower_text = (text or '').lower()
        if status_code == 401 or 'unauthorized' in lower_text:
            return '[GS-401] Falha de Autenticação — o plugin não conseguiu autenticar ou não tem acesso para realizar esta operação no GeoServer (Erro 401 Unauthorized).'
        if status_code == 403:
            return '[GS-403] Acesso Negado — você não possui permissão de escrita neste Workspace.'
        if status_code == 404:
            return '[GS-404] Workspace ou Datastore não encontrado.'
        if 'already exists' in lower_text and 'style' in lower_text:
            return '[GS-409] Já existe um estilo com esse nome neste workspace.'
        if 'already exists' in lower_text:
            return '[GS-409] Já existe uma camada com esse nome neste datastore.'
        if 'unable to parse' in lower_text or 'invalid style' in lower_text or 'error persisting' in lower_text:
            return (
                '[GS-422] O GeoServer não conseguiu interpretar o SLD enviado. Se o estilo foi gerado '
                'do QGIS, a simbologia da camada pode não ter equivalente SLD - simplifique o '
                'estilo no QGIS ou use um arquivo .sld válido.'
            )
        if 'no attributes were specified' in lower_text:
            return (
                '[GS-422] O GeoServer não encontrou colunas para esta tabela no datastore selecionado. '
                'Causas mais comuns: (1) o Schema configurado nas Connection Parameters do '
                'datastore no GeoServer é diferente do schema onde a tabela vive no banco '
                '(veja o "schema.table" mostrado no card da camada), ou (2) a tabela não tem '
                'chave primária (obrigatória para publicação).'
            )
        return f'[GS-{status_code or "000"}] {(text or "Erro inesperado do GeoServer.")[:400]}'

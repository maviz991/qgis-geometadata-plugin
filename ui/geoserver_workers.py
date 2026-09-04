# -*- coding: utf-8 -*-
"""
geoserver_workers.py - GeoMetadata Plugin
=====================================
Workers (QThread) usados pelo GeoServerBridge - chamadas REST que não podem
bloquear a UI do QGIS (RNF02 de requisitos_v2.md).
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal

try:
    import psycopg2
except ImportError:
    psycopg2 = None
# Overrides built-in print for this module to prevent QGIS segfaults from background threads
def print(*args, **kwargs):
    pass


class _GsSearchLayersWorker(QThread):
    """Busca TODAS as camadas do GeoServer via WMS GetCapabilities (RNF02 - essa chamada de
    rede rodava direto no pyqtSlot, na main thread, sem QThread nenhuma - GetCapabilities
    pode ter uma resposta grande/lenta dependendo do tamanho do catálogo, travando a
    QWebEngineView inteira, tanto ao abrir a busca quanto a cada letra digitada enquanto a
    1ª busca da sessão ainda estava em voo). O resultado completo (não filtrado) é devolvido
    pro bridge cachear (GeoServerBridge._geoserver_layers_cache) - só a PRIMEIRA busca de
    cada sessão paga esse custo de rede; buscas seguintes filtram o cache já carregado, sem
    I/O nenhum, por isso continuam síncronas no bridge.

    geoserver_service (opcional) - quando presente e com sessão REST configurada (login já
    feito), a requisição usa essa sessão autenticada em vez de ir anônima: o GeoServer
    aplica segurança de dados (data security) por workspace/camada no próprio WMS, e uma
    chamada anônima só enxerga o que estiver liberado pra "sem autenticação" - normalmente
    UM workspace público só, nunca o catálogo inteiro. Sem isso, a busca "sumia" quase todo
    o catálogo mesmo com o usuário logado no plugin, porque essa chamada nunca usava a
    sessão de verdade. Sem geoserver_service (ou sem sessão ainda, ex.: GN "Recursos
    associados" antes de logar), cai pro mesmo fallback anônimo de sempre."""
    done = pyqtSignal(list, str)  # camadas (sem filtro), erro

    def __init__(self, geoserver_url, geoserver_service=None):
        super().__init__()
        self._geoserver_url = geoserver_url
        self._service = geoserver_service

    def _fetch_capabilities(self, caps_url):
        if self._service is not None:
            try:
                session = self._service._get_rest_session()
            except Exception:
                session = None
            if session is not None:
                import requests
                from ..core.http_lock import HTTP_SESSION_LOCK
                with HTTP_SESSION_LOCK:
                    response = session.get(caps_url, timeout=60, verify=False)
                response.raise_for_status()
                return response.content
        import ssl
        import urllib.request
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        # 60s (não 15s) - agora que roda em QThread, um timeout maior não trava mais a tela
        # (era o problema original) - só demora mais a responder em catálogos grandes/
        # servidor lento, o que é preferível a um timeout curto demais estourando à toa
        # (visto em uso real: "The read operation timed out" com 15s).
        req = urllib.request.Request(caps_url, headers={'User-Agent': 'GeoMetadataPlugin/1.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            return resp.read()

    def run(self):
        try:
            import xml.etree.ElementTree as ET

            base_url = (self._geoserver_url or '').rstrip('/')
            if not base_url:
                self.done.emit([], 'geoserver_url não configurado.')
                return
            caps_url = f"{base_url}/wms?service=WMS&version=1.3.0&request=GetCapabilities"

            content = self._fetch_capabilities(caps_url)

            root = ET.fromstring(content)
            all_layers = []
            for layer_el in root.iter():
                tag_local = layer_el.tag.split('}')[-1] if '}' in layer_el.tag else layer_el.tag
                if tag_local != 'Layer':
                    continue
                name_el = title_el = None
                for child in layer_el:
                    ct = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if ct == 'Name'  and name_el  is None: name_el  = child
                    if ct == 'Title' and title_el is None: title_el = child
                name  = (name_el.text  or '').strip() if name_el  is not None else ''
                title = (title_el.text or '').strip() if title_el is not None else ''
                if not name or ':' not in name:
                    continue
                workspace = name.split(':', 1)[0]
                all_layers.append({
                    'name':      name,
                    'workspace': workspace,
                    'title':     title or name,
                    'wms_url':   f"{base_url}/{workspace}/wms?service=WMS",
                    'wfs_url':   f"{base_url}/{workspace}/wfs?service=WFS",
                })
            self.done.emit(all_layers, '')
        except Exception as exc:
            self.done.emit([], self._translate_error(exc))

    @staticmethod
    def _translate_error(exc):
        """Traduz os erros mais comuns dessa busca - GetCapabilities pode ter uma resposta
        grande (catálogo com muitas camadas); timeout/conexão são os casos mais prováveis
        de aparecerem pro usuário aqui. Cobre tanto o caminho anônimo (urllib) quanto o
        autenticado (requests, quando geoserver_service tem sessão) - os dois podem
        estourar timeout/conexão; erro de autenticação (401/403) vindo do path autenticado
        cai no fallback genérico (str(exc)) abaixo, sem tradução especial ainda."""
        import socket
        import urllib.error
        try:
            import requests
            if isinstance(exc, requests.exceptions.Timeout):
                return 'O GeoServer demorou demais pra responder (timeout) - o catálogo pode estar grande ou o servidor lento agora. Tente de novo.'
            if isinstance(exc, requests.exceptions.ConnectionError):
                return f'Não foi possível conectar ao GeoServer: {exc}.'
        except ImportError:
            pass
        if isinstance(exc, socket.timeout):
            return 'O GeoServer demorou demais pra responder (timeout) - o catálogo pode estar grande ou o servidor lento agora. Tente de novo.'
        if isinstance(exc, urllib.error.URLError):
            reason = getattr(exc, 'reason', None)
            if isinstance(reason, socket.timeout):
                return 'O GeoServer demorou demais pra responder (timeout) - o catálogo pode estar grande ou o servidor lento agora. Tente de novo.'
            return f'Não foi possível conectar ao GeoServer: {reason or exc}.'
        return str(exc)



def _gs_augment_404(exc, workspace=None, datastore=None, published_name=None):
    """Acrescenta uma dica acionável quando o erro de uma ação de "Atualizar" (Camada ou
    Estilo - as duas só fazem sentido numa camada JÁ publicada, via PUT) vem de um 404
    ([GS-404], ver GeoServerService.translate_gs_error): nesse contexto específico, "não
    encontrado" quase sempre significa que a camada não existe de fato nesse Workspace/
    Datastore no GeoServer (nunca foi publicada, ou foi removida/renomeada desde a última
    vez) - não um erro genérico de configuração. Não mexe no texto de outros erros.

    workspace/datastore/published_name (opcionais) - quando informados, entram na mensagem
    pra deixar claro EXATAMENTE qual destino foi tentado (facilita diagnosticar se o valor
    restaurado do rascunho/formulário está errado, em vez de um "não encontrado" genérico
    sem dizer o quê)."""
    message = str(exc)
    if '[GS-404]' in message:
        target = ''
        if workspace or datastore or published_name:
            target = f' ("{workspace or "?"}/{datastore or "?"}/{published_name or "?"}")'
        message += (
            f'<br><br>Isso costuma significar que essa camada{target} não existe de fato '
            'nesse Workspace/Datastore no GeoServer agora (nunca foi publicada, ou foi '
            'removida/renomeada desde a última vez). Confira a aba Destino e use "Serviços > '
            'Publicar Camada" se for o caso.'
        )
    return message


def _build_gn_metadata_link_url(uuid, config_loader_instance):
    """Mesma fórmula de GeoServerBridge._build_metadata_link_url (geoserver_bridge.py) -
    duplicada aqui (não importada) pra evitar import circular (geoserver_bridge.py já
    importa deste módulo). As duas precisam concordar - é o mesmo link que a publicação de
    verdade grava no GeoServer."""
    if not uuid:
        return ''
    records_url = (config_loader_instance.get_geonetwork_url() or {}).get('records_url')
    if not records_url:
        return ''
    return f"{records_url}/{uuid}/formatters/xml"


def _resolve_gn_metadata_uuid(candidate_uuid, ws_layer_name, geonetwork_service, config_loader_instance):
    """Resolve o metadado GN pra uma camada puxada do GeoServer, em duas etapas: (1)
    confirma o candidato vindo do próprio metadataLinks da camada (existe só quando ela JÁ
    foi publicada por este plugin com o link certo gravado) buscando o registro completo
    (fetch_from_geonetwork); (2) se não achou nada (camada nunca teve esse link - o caso
    mais comum na prática, publicada ANTES do metadado existir, pedido explícito do
    usuário: "se puxar GS tenta no GN"), cai pra uma busca REVERSA no GeoNetwork por um
    registro que referencie essa camada (GeoNetworkService.
    find_metadata_uuid_by_layer_reference) - não precisa que o usuário tenha aberto esse
    registro no editor GN antes.

    Retorna (uuid, record) - record é o dict completo (mesmo formato de
    xml_parser.parse_xml_to_dict: title/abstract/MD_Keywords/etc.) do registro confirmado,
    pra popular o formulário GS sozinho com o que está de fato no GeoNetwork (pedido do
    usuário - já que o vínculo foi confirmado, usa o conteúdo em vez de só mostrar o link).
    ('', None) se não achou/confirmou nada em nenhuma das duas etapas."""
    uuid = (candidate_uuid or '').strip()
    if uuid and geonetwork_service:
        try:
            record = geonetwork_service.fetch_from_geonetwork(uuid, config_loader_instance)
        except Exception as exc:
            print(f"GeoMetadata [_resolve_gn_metadata_uuid] falha ao confirmar uuid {uuid!r}: {exc}")
            record = None
        if record:
            return uuid, record
    if not geonetwork_service or not ws_layer_name:
        return '', None
    try:
        found_uuid = geonetwork_service.find_metadata_uuid_by_layer_reference(ws_layer_name, config_loader_instance)
    except Exception as exc:
        print(f"GeoMetadata [_resolve_gn_metadata_uuid] busca reversa falhou pra {ws_layer_name!r}: {exc}")
        found_uuid = None
    if not found_uuid:
        return '', None
    try:
        record = geonetwork_service.fetch_from_geonetwork(found_uuid, config_loader_instance)
    except Exception as exc:
        print(f"GeoMetadata [_resolve_gn_metadata_uuid] falha ao buscar conteúdo de {found_uuid!r}: {exc}")
        record = None
    return (found_uuid, record) if record else ('', None)


def _apply_gn_metadata_to_remote(remote, gn_uuid, gn_record, config_loader_instance):
    """Aplica o resultado de _resolve_gn_metadata_uuid direto no dict que os workers de
    pull devolvem pro JS - `metadata_uuid`/`metadata_link_url` (mesma fórmula usada na
    publicação de verdade, pra prévia bater com o que vai ser gravado) sempre, e
    título/resumo/palavras-chave do registro GN só quando o GeoServer não tinha NADA
    preenchido pra esses campos (pedido do usuário: "popular formulário auto" já que o
    vínculo foi confirmado - mas sem sobrescrever um título/resumo que a própria camada no
    GeoServer já tinha, mais provável de já ser intencional)."""
    remote['metadata_uuid'] = gn_uuid
    remote['metadata_link_url'] = _build_gn_metadata_link_url(gn_uuid, config_loader_instance)
    if gn_record:
        if not remote.get('title') and gn_record.get('title'):
            remote['title'] = gn_record['title']
        if not remote.get('abstract') and gn_record.get('abstract'):
            remote['abstract'] = gn_record['abstract']
        if not remote.get('keywords') and gn_record.get('MD_Keywords'):
            remote['keywords'] = gn_record['MD_Keywords']


class _GsWorkspacesWorker(QThread):
    """Lista os workspaces do GeoServer em background (RF01)."""
    done = pyqtSignal(list, str)  # workspaces, error

    def __init__(self, geoserver_service, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._config = config_loader_instance

    def run(self):
        try:
            workspaces = self._service.list_workspaces(self._config)
            self.done.emit(workspaces, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsDatastoresWorker(QThread):
    """Lista os datastores de um workspace do GeoServer em background (RF01)."""
    done = pyqtSignal(list, str)  # datastores, error

    def __init__(self, geoserver_service, workspace, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._config = config_loader_instance

    def run(self):
        try:
            datastores = self._service.list_datastores(self._workspace, self._config)
            self.done.emit(datastores, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsFeatureTypesWorker(QThread):
    """Lista as tabelas visíveis (list=all) de um datastore em background - usado pra
    validar, antes de publicar, se a tabela da camada ativa existe ali (ver
    GeoServerService.list_featuretypes)."""
    done = pyqtSignal(list, str)  # nomes, error

    def __init__(self, geoserver_service, workspace, datastore, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._config = config_loader_instance

    def run(self):
        try:
            names = self._service.list_featuretypes(self._workspace, self._datastore, self._config)
            self.done.emit(names, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsPublishedFeatureTypesWorker(QThread):
    """Lista só as camadas JÁ PUBLICADAS de um datastore em background - usado pelo
    seletor "Selecionar camada publicada" (aba Destino) pra filtrar a lista quando
    Workspace/Datastore já estão escolhidos (ver GeoServerService.
    list_published_featuretypes - diferente de _GsFeatureTypesWorker/list_featuretypes,
    que usa list=all e inclui tabelas nunca publicadas)."""
    done = pyqtSignal(list, str)  # nomes, error

    def __init__(self, geoserver_service, workspace, datastore, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._config = config_loader_instance

    def run(self):
        try:
            names = self._service.list_published_featuretypes(self._workspace, self._datastore, self._config)
            self.done.emit(names, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsFindDatastoreWorker(QThread):
    """Varre todos os workspaces/datastores procurando onde a tabela da camada ativa
    está visível (botão "Detectar automaticamente" - ver GeoServerService.
    find_datastore_for_table). Pode demorar bem mais que os outros workers (1 chamada por
    workspace + 1 por datastore), por isso emite progress() a cada workspace verificado."""
    progress = pyqtSignal(str)  # mensagem de status
    done = pyqtSignal(list, str)  # [{'workspace':..., 'datastore':...}, ...], error

    def __init__(self, geoserver_service, table_name, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._table_name = table_name
        self._config = config_loader_instance

    def run(self):
        try:
            matches = self._service.find_datastore_for_table(
                self._table_name, self._config, progress_callback=self.progress.emit
            )
            self.done.emit(matches, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsPublishWorker(QThread):
    """Registra uma tabela PostGIS já existente como FeatureType no GeoServer (RF02) e,
    quando há uma tarefa de estilo (style_task, ver GeoServerBridge._prepare_style_task),
    sobe/associa o SLD como estilo padrão logo em seguida - tudo fora da UI thread (RNF02).
    Falha no ESTILO não derruba a publicação (que já deu certo): emite sucesso=True com a
    mensagem de aviso preenchida - o JS mostra o aviso e o bridge NÃO grava os campos de
    estilo no banco (pro badge continuar acusando a pendência)."""
    done = pyqtSignal(bool, str, str)  # sucesso, mensagem (erro OU aviso de estilo), nome_publicado

    def __init__(self, geoserver_service, workspace, datastore, native_table_name, published_name,
                 title, abstract, keywords, config_loader_instance, style_task=None, srs=None,
                 metadata_link_url=None):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._native_table_name = native_table_name
        self._published_name = published_name
        self._title = title
        self._abstract = abstract
        self._keywords = keywords
        self._config = config_loader_instance
        self._style_task = style_task
        self._srs = srs
        self._metadata_link_url = metadata_link_url

    def run(self):
        try:
            self._service.register_postgis_featuretype(
                self._workspace, self._datastore, self._native_table_name,
                self._published_name, self._config, self._title, self._abstract, self._keywords,
                srs=self._srs, metadata_link_url=self._metadata_link_url
            )
        except Exception as exc:
            self.done.emit(False, str(exc), self._published_name)
            return
        style_warning = ''
        if self._style_task:
            try:
                self._service.apply_style(self._workspace, self._published_name, self._style_task, self._config)
            except Exception as exc:
                style_warning = (
                    'A camada foi publicada, mas o estilo não pôde ser aplicado: ' + str(exc) +
                    '<br><br>Ajuste a aba Estilos e publique de novo pra tentar outra vez.'
                )
        self.done.emit(True, style_warning, self._published_name)


class _GsPullLayerWorker(QThread):
    """"Serviços > Baixar Camada" (banner "Atualização disponível", como o GN) - PULL,
    não push: busca o que está DE FATO publicado no GeoServer agora (título/resumo/
    palavras-chave via fetch_published_featuretype, estilo padrão/adicionais via
    fetch_layer_styles - as duas só leitura, já usadas pelo badge) e devolve pro bridge
    aplicar no formulário local. Existe porque, num fluxo com mais de um técnico na mesma
    camada, "diferente do servidor" pode significar que ALGUÉM MAIS publicou depois de
    você - nesse caso empurrar o formulário local (desatualizado) sobrescreveria o
    trabalho de quem publicou por último. Ver GeoServerService.fetch_published_featuretype/
    fetch_layer_styles.

    workspace/datastore vêm do FORMULÁRIO (aba Destino - pode ter sido restaurado de um
    rascunho antigo, ver docs_projeto/bugs.md Bug 52), não recalculados a cada vez -
    diferente de _GsPullLayerByWmsNameWorker (busca/link WMS do GN), que sempre re-descobre
    o datastore do zero via find_datastore_for_published_name. Se o datastore salvo não
    bater mais (nome mudou, ou o rascunho ficou com um valor desatualizado/errado), CAI
    NESSE MESMO mecanismo de re-descoberta como fallback, em vez de falhar de cara - usa
    workspace+published_name (o "id" estável, ver comentário do usuário nos bugs) pra
    re-achar o datastore atual, e reporta o valor CORRIGIDO de volta (remote['datastore'])
    pro JS reaplicar no formulário/rascunho - autocorrige o desalinhamento em vez de só
    apontar o erro toda vez."""
    done = pyqtSignal(bool, 'QVariant', str)  # sucesso, dados (title/abstract/keywords/default_style/...), erro

    def __init__(self, geoserver_service, workspace, datastore, published_name, config_loader_instance,
                 geonetwork_service=None):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._published_name = published_name
        self._config = config_loader_instance
        self._geonetwork_service = geonetwork_service

    def run(self):
        try:
            datastore = self._datastore
            remote = self._service.fetch_published_featuretype(
                self._workspace, datastore, self._published_name, self._config
            )
            redetected = False
            if remote is None:
                try:
                    fresh_datastore = self._service.find_datastore_for_published_name(
                        self._workspace, self._published_name, self._config
                    )
                except Exception as exc:
                    fresh_datastore = None
                    print(f"GeoMetadata [_GsPullLayerWorker] re-detecção de datastore falhou: {exc}")
                if fresh_datastore and fresh_datastore != datastore:
                    datastore = fresh_datastore
                    redetected = True
                    remote = self._service.fetch_published_featuretype(
                        self._workspace, datastore, self._published_name, self._config
                    )
            if remote is None:
                self.done.emit(False, {}, (
                    f'[GS-404] "{self._workspace}/{self._datastore}/{self._published_name}" não foi '
                    'encontrada no GeoServer agora - pode nunca ter sido publicada, ou ter sido '
                    'removida/renomeada. Confira a aba Destino e use "Serviços > Publicar Camada" se '
                    'for o caso.'
                ))
                return
            if redetected:
                remote['workspace'] = self._workspace
                remote['datastore'] = datastore
                remote['published_name'] = self._published_name
            # Resolve o metadado GN pra essa camada - confirma o candidato do metadataLinks
            # (link gravado numa publicação anterior por este plugin) e, se não achar nada
            # (caso mais comum: camada publicada ANTES do metadado existir), cai pra busca
            # reversa no GN por quem referencia essa camada (Bug 58/59, docs_projeto/
            # bugs.md - pedido explícito do usuário: "se puxar GS tenta no GN"). Popula
            # título/resumo/palavras-chave vazios com o conteúdo do GN confirmado.
            gn_uuid, gn_record = _resolve_gn_metadata_uuid(
                remote.get('metadata_uuid'), f"{self._workspace}:{self._published_name}",
                self._geonetwork_service, self._config
            )
            _apply_gn_metadata_to_remote(remote, gn_uuid, gn_record, self._config)
            # Estilo isolado em try/except próprio - mesmo raciocínio de _GsSyncCheckWorker:
            # uma falha aqui não pode jogar fora o título/resumo/palavras-chave já obtidos.
            styles = None
            try:
                styles = self._service.fetch_layer_styles(self._workspace, self._published_name, self._config)
            except Exception as style_exc:
                print(f"GeoMetadata [_GsPullLayerWorker] fetch_layer_styles: {style_exc}")
            remote['default_style'] = (styles or {}).get('default_style') or ''
            remote['default_style_workspace'] = (styles or {}).get('default_style_workspace') or ''
            remote['additional_styles'] = (styles or {}).get('additional') or []
            self.done.emit(True, remote, '')
        except Exception as exc:
            self.done.emit(False, {}, str(exc))


class _GsPullLayerByWmsNameWorker(QThread):
    """"Serviços > Baixar Camada" quando não há camada PostGIS ativa no QGIS mas o usuário
    já fez pull do GeoNetwork e o metadado tem um link WMS/WFS com o nome da camada no
    formato workspace:published_name (CI_OnlineResource name, xml_parser.py wms_data).

    Fluxo: (1) extrai workspace/published_name do ws_layer_name, (2) descobre o datastore
    via GeoServerService.find_datastore_for_published_name (tenta fetch_published_featuretype
    em cada datastore do workspace), (3) faz fetch_published_featuretype + fetch_layer_styles
    normalmente. Emite done(bool, QVariant, str) — mesmo assinatura de _GsPullLayerWorker,
    permitindo o mesmo handler (GeoServerBridge._on_layer_pulled) e o mesmo sinal (gs_layer_pulled)."""
    progress = pyqtSignal(str)   # mensagem de status para _showActionLoading no JS
    done = pyqtSignal(bool, 'QVariant', str)  # sucesso, dados, erro

    def __init__(self, geoserver_service, ws_layer_name, config_loader_instance, geonetwork_service=None):
        super().__init__()
        self._service = geoserver_service
        self._ws_layer_name = ws_layer_name      # 'workspace:published_name' do link WMS
        self._config = config_loader_instance
        self._geonetwork_service = geonetwork_service
        self._workspace = ''
        self._datastore = ''
        self._published_name = ''

    def run(self):
        try:
            # Extrai workspace:published_name (formato padrão GeoServer: 'ws:nome')
            if ':' not in (self._ws_layer_name or ''):
                self.done.emit(False, {}, (
                    'Nome de camada do link WMS/WFS inválido: esperado "workspace:nome" '
                    f'(recebido: "{self._ws_layer_name}"). Verifique o metadado no GeoNetwork.'
                ))
                return
            workspace, published_name = self._ws_layer_name.split(':', 1)
            self._workspace = workspace
            self._published_name = published_name

            # Descobre o datastore varrendo os datastores do workspace
            self.progress.emit(f'Buscando em qual datastore "{workspace}:{published_name}" está publicado...')
            datastore = self._service.find_datastore_for_published_name(
                workspace, published_name, self._config,
                progress_callback=self.progress.emit
            )
            if not datastore:
                self.done.emit(False, {}, (
                    f'Camada "{workspace}:{published_name}" não foi encontrada em nenhum datastore '
                    f'do workspace "{workspace}" no GeoServer. Verifique se o link WMS/WFS no '
                    'metadado (GeoNetwork) aponta para a camada correta.'
                ))
                return
            self._datastore = datastore

            # Pull normal: mesma lógica de _GsPullLayerWorker daqui pra frente
            self.progress.emit(f'Baixando dados publicados de "{workspace}/{datastore}/{published_name}"...')
            remote = self._service.fetch_published_featuretype(
                workspace, datastore, published_name, self._config
            )
            if remote is None:
                self.done.emit(False, {}, (
                    f'[GS-404] "{workspace}:{published_name}" sumiu do datastore "{datastore}" '
                    'durante a busca. Tente novamente ou verifique o GeoServer.'
                ))
                return
            # Resolve o metadado GN (confirma o candidato do metadataLinks, cai pra busca
            # reversa se não achar, popula título/resumo/palavras-chave vazios - mesmo
            # raciocínio de _GsPullLayerWorker, ver Bug 58/59, docs_projeto/bugs.md).
            gn_uuid, gn_record = _resolve_gn_metadata_uuid(
                remote.get('metadata_uuid'), f"{workspace}:{published_name}",
                self._geonetwork_service, self._config
            )
            _apply_gn_metadata_to_remote(remote, gn_uuid, gn_record, self._config)
            styles = None
            try:
                styles = self._service.fetch_layer_styles(workspace, published_name, self._config)
            except Exception as style_exc:
                print(f'GeoMetadata [_GsPullLayerByWmsNameWorker] fetch_layer_styles: {style_exc}')
            remote['workspace'] = workspace
            remote['datastore'] = datastore
            remote['published_name'] = published_name
            remote['default_style'] = (styles or {}).get('default_style') or ''
            remote['default_style_workspace'] = (styles or {}).get('default_style_workspace') or ''
            remote['additional_styles'] = (styles or {}).get('additional') or []
            self.done.emit(True, remote, '')
        except Exception as exc:
            self.done.emit(False, {}, str(exc))


class _GsStylesWorker(QThread):
    """Lista os estilos disponíveis (globais + do workspace) em background - popula o
    select "Usar estilo existente" da aba Estilos (ver GeoServerService.list_styles)."""
    done = pyqtSignal(list, str)  # [{'name':..., 'workspace': ''|ws}], error

    def __init__(self, geoserver_service, workspace, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._config = config_loader_instance

    def run(self):
        try:
            styles = self._service.list_styles(self._workspace, self._config)
            self.done.emit(styles, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsSyncCheckWorker(QThread):
    """Confere ao vivo (REST, GeoServerService.fetch_published_featuretype) se o
    formulário bate com o que está DE FATO publicado no GeoServer agora - nível 'sistema'
    do badge (ver GeoServerBridge.check_gs_sync). Chamada de rede isolada da UI thread
    (RNF02) - antes rodava direto no slot pyqtSlot, travando o painel GS inteiro enquanto
    esperava a resposta."""
    done = pyqtSignal('QVariant')  # {'state': 'sys_synced'|'sys_modified'|'sys_not_found'|'error', 'workspace':, 'datastore':, 'published_name':, [+ 'title'/'abstract'/'keywords' ao vivo quando encontrado]}

    def __init__(self, geoserver_service, workspace, datastore, published_name, title, abstract, keywords, config_loader_instance, style_cfg=None):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._published_name = published_name
        self._title = title
        self._abstract = abstract
        self._keywords = keywords
        self._config = config_loader_instance
        self._style_cfg = style_cfg

    def run(self):
        # workspace/datastore/published_name sempre presentes no resultado - o JS usa isso
        # pra confirmar que a resposta ainda corresponde à checagem que ele espera (camada/
        # destino pode ter trocado enquanto essa chamada estava em voo).
        base = {'workspace': self._workspace, 'datastore': self._datastore, 'published_name': self._published_name}
        try:
            remote = self._service.fetch_published_featuretype(
                self._workspace, self._datastore, self._published_name, self._config
            )
            if remote is None:
                base['state'] = 'sys_not_found'
                self.done.emit(base)
                return
            remote_kw = sorted((k or '').strip() for k in (remote.get('keywords') or []))
            local_kw = sorted((k or '').strip() for k in (self._keywords or []))
            title_match = (remote.get('title') or '').strip() == (self._title or '').strip()
            abstract_match = (remote.get('abstract') or '').strip() == (self._abstract or '').strip()
            kw_match = remote_kw == local_kw
            matches = title_match and abstract_match and kw_match
            # Log de diagnóstico temporário (não é logging permanente do projeto) - "matches"
            # antes era um booleano só, sem dizer QUAL campo diverge; imprime os dois lados
            # só quando dá falso, pra não gerar ruído numa checagem que bateu certinho.
            if not matches:
                print(
                    f"GeoMetadata [_GsSyncCheckWorker] DIVERGÊNCIA título/resumo/keywords - "
                    f"title: match={title_match} remoto={remote.get('title')!r} local={self._title!r} | "
                    f"abstract: match={abstract_match} remoto={remote.get('abstract')!r} local={self._abstract!r} | "
                    f"keywords: match={kw_match} remoto={remote_kw!r} local={local_kw!r}"
                )
            base.update(remote)

            # Checagem de estilos ao vivo - isolada em try/except próprio: uma falha aqui
            # (timeout, layer ainda não exposta como resource /rest/layers logo após
            # publicar, etc.) não pode derrubar a checagem inteira pra 'error' e descartar
            # o resultado (já calculado acima) do match de título/resumo/palavras-chave.
            remote_styles = None
            try:
                remote_styles = self._service.fetch_layer_styles(
                    self._workspace, self._published_name, self._config
                )
            except Exception as style_exc:
                print(f"GeoMetadata [_GsSyncCheckWorker] fetch_layer_styles: {style_exc}")

            styles_match = True
            if remote_styles is not None:
                base['remote_default_style'] = remote_styles.get('default_style')
                base['remote_default_style_workspace'] = remote_styles.get('default_style_workspace')
                base['remote_additional_styles'] = remote_styles.get('additional') or []

                # Só compara quando conseguimos buscar o estado remoto de verdade - sem
                # isso (fetch falhou ou a camada não existe como 'layer' resource),
                # styles_match fica True (mesmo comportamento de antes dessa feature
                # existir) em vez de acusar divergência por uma checagem que não rodou.
                if self._style_cfg:
                    from .geoserver_bridge import GeoServerBridge
                    d_src, d_nm, d_ws, adds_json = GeoServerBridge.derive_style_fields(self._style_cfg, self._workspace)
                    if d_src:
                        r_def = remote_styles.get('default_style') or ''
                        if r_def != d_nm:
                            styles_match = False
                            print(f"GeoMetadata [_GsSyncCheckWorker] DIVERGÊNCIA estilo padrão - remoto={r_def!r} local(d_nm)={d_nm!r} style_cfg={self._style_cfg!r}")

                        if styles_match:
                            import json
                            adds = json.loads(adds_json) if adds_json else []
                            r_adds = remote_styles.get('additional') or []
                            r_adds_list = [(a.get('name') or '', a.get('style_workspace') or '') for a in r_adds]
                            # workspace vazio só cai pro workspace de publicação quando o
                            # estilo foi CRIADO nessa publicação ('file'/'qgis' - aí sim
                            # sempre nasce no workspace de destino, mesma regra de
                            # derive_style_fields/_extract). Pra um estilo 'existing'
                            # (já existente, escolhido da lista), workspace vazio é um
                            # ESTILO GLOBAL de verdade - forçar o workspace de publicação
                            # aqui inventava uma divergência contra o lado remoto (que
                            # corretamente reporta '' pra estilo global).
                            local_adds_list = [
                                (
                                    a.get('existing_name') or a.get('name') or '',
                                    (a.get('existing_workspace') or '') if a.get('source') == 'existing' else self._workspace
                                )
                                for a in adds
                            ]

                            if len(r_adds_list) != len(local_adds_list):
                                styles_match = False
                                print(f"GeoMetadata [_GsSyncCheckWorker] DIVERGÊNCIA estilos adicionais (quantidade) - remoto={r_adds_list!r} local={local_adds_list!r}")
                            else:
                                for la in local_adds_list:
                                    if la not in r_adds_list:
                                        styles_match = False
                                        print(f"GeoMetadata [_GsSyncCheckWorker] DIVERGÊNCIA estilos adicionais (item) - remoto={r_adds_list!r} local={local_adds_list!r}")
                                        break

            base['state'] = 'sys_synced' if (matches and styles_match) else 'sys_modified'
            self.done.emit(base)
        except Exception as exc:
            print(f"GeoMetadata [_GsSyncCheckWorker]: {exc}")
            # base (workspace/datastore/published_name) preservado mesmo no erro - ver
            # comentário equivalente em GeoServerBridge.check_gs_sync sobre a resposta
            # precisar bater a key esperada em _onGsSyncChecked (geoserver.js).
            base['state'] = 'error'
            self.done.emit(base)


class _GsActiveLayerInfoWorker(QThread):
    """Busca em background o que está salvo no banco pra camada ativa (metadado MGB +
    destino de publicação GS, GeoServerService.fetch_saved_records) e, se achar um uuid,
    o metadado AO VIVO no GeoNetwork - usado por GeoServerBridge.get_active_layer_publish_info.
    Antes essa busca rodava toda inteira, síncrona, dentro do próprio pyqtSlot (duas
    conexões psycopg2 + potencialmente uma chamada REST ao GeoNetwork, todas bloqueantes) -
    travava a UI inteira (Qt event loop, inclusive o compositor da QWebEngineView) toda vez
    que o painel GS abria ou a camada ativa mudava, sem exceção (RNF02 - mesmo motivo de
    _GsSyncCheckWorker). Só recebe dados já resolvidos na main thread (conn_params via
    resolve_layer_db_params, uuid_hint já combinando draft+hint) - nada aqui toca a API do
    QGIS (QgsVectorLayer etc.), que não é thread-safe."""
    done = pyqtSignal('QVariant')  # {'local_metadata': dict|None, 'saved_destination': dict|None, 'gn_remote': dict|None, 'db_error': bool}

    def __init__(self, conn_params, f_table_catalog, f_table_schema, f_table_name,
                 uuid_hint, geonetwork_service, config_loader_instance):
        super().__init__()
        self._conn_params = conn_params
        self._f_table_catalog = f_table_catalog
        self._f_table_schema = f_table_schema
        self._f_table_name = f_table_name
        self._uuid_hint = uuid_hint
        self._geonetwork_service = geonetwork_service
        self._config = config_loader_instance

    def run(self):
        from ..core.geoserver_service import GeoServerService
        local_metadata, saved_destination = None, None
        db_error = False
        try:
            local_metadata, saved_destination = GeoServerService.fetch_saved_records(
                self._conn_params, self._f_table_catalog, self._f_table_schema, self._f_table_name
            )
        except Exception as exc:
            if psycopg2 and isinstance(exc, psycopg2.OperationalError):
                # Banco inacessível agora (ver fetch_saved_records) - diferente de "nada
                # salvo" - GeoServerBridge._on_layer_info_ready repassa esse flag pro JS
                # avisar o usuário em vez de mostrar "Não Encontrado" silenciosamente.
                db_error = True
            else:
                print(f"GeoMetadata [_GsActiveLayerInfoWorker] banco: {exc}")

        # Mesma prioridade de uuid de antes (_load_layer_metadata): metadata_uuid do banco
        # primeiro, senão o hint (que já embute o do rascunho local, resolvido na main
        # thread antes de disparar esse worker - ver get_active_layer_publish_info).
        gn_remote = None
        uuid = (local_metadata or {}).get('metadata_uuid') or self._uuid_hint or None
        if uuid and self._geonetwork_service:
            try:
                gn_remote = self._geonetwork_service.fetch_from_geonetwork(uuid, self._config)
            except Exception as exc:
                print(f"GeoMetadata [_GsActiveLayerInfoWorker] GeoNetwork: {exc}")

        self.done.emit({
            'local_metadata': local_metadata,
            'saved_destination': saved_destination,
            'gn_remote': gn_remote,
            'db_error': db_error,
        })


class _GsUpdateMetadataWorker(QThread):
    """Atualiza título/resumo/palavras-chave/link de metadados (PUT, sem republicar o
    FeatureType) e, se houver style_task, aplica o estilo logo em seguida - usado tanto
    pelo fallback "sem camada ativa" (GeoServerBridge.update_layer_metadata) quanto por
    "Publicar Camada" com camada ativa quando o destino JÁ está publicado (ver
    GeoServerBridge.publish_layer - detecta isso via fetch_published_featuretype antes de
    decidir entre criar ou atualizar, mesma filosofia do "Publicar Metadados" do GN: uma
    ação só, cria OU atualiza, sem exigir um botão "Atualizar Estilo" à parte).

    Mesma convenção de _GsPublishWorker: falha SÓ no estilo não derruba o resultado geral
    (os metadados já foram atualizados de verdade) - emite sucesso=True com a mensagem de
    aviso preenchida; mensagem vazia = sucesso completo, sem nada a avisar."""
    done = pyqtSignal(bool, str)  # sucesso, mensagem (erro OU aviso de estilo, '' = sem ressalvas)

    def __init__(self, geoserver_service, workspace, datastore, published_name, title, abstract, keywords, style_task,
                 config_loader_instance, metadata_link_url=''):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._published_name = published_name
        self._title = title
        self._abstract = abstract
        self._keywords = keywords
        self._style_task = style_task
        self._config = config_loader_instance
        self._metadata_link_url = metadata_link_url

    def run(self):
        try:
            self._service.update_published_featuretype(
                self._workspace, self._datastore, self._published_name, self._config,
                title=self._title, abstract=self._abstract, keywords=self._keywords,
                metadata_link_url=self._metadata_link_url
            )
        except Exception as exc:
            self.done.emit(False, _gs_augment_404(exc, self._workspace, self._datastore, self._published_name))
            return

        style_warning = ''
        if self._style_task:
            try:
                self._service.apply_style(self._workspace, self._published_name, self._style_task, self._config)
            except Exception as exc:
                style_warning = (
                    'Os metadados foram atualizados, mas o estilo não pôde ser aplicado: ' + str(exc) +
                    '<br><br>Ajuste a aba Estilos e publique/atualize de novo pra tentar outra vez.'
                )
        self.done.emit(True, style_warning)

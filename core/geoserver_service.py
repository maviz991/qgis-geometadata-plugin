import re
import unicodedata

import requests


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


class GeoServerService:
    """
    Serviço que abstrai a comunicação com o GeoServer (API REST). Espelha o padrão
    de core/geonetwork_service.py - nenhuma dependência de Qt aqui, só requests puro.
    """
    def __init__(self, plugin):
        self.plugin = plugin

    def list_workspaces(self, config_loader_instance):
        """RF01 - lista os workspaces disponíveis no GeoServer."""
        api_session = self.plugin.api_session
        if not api_session:
            raise Exception("Sessão da API não foi inicializada. Faça login primeiro.")

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        response = api_session.get(
            f"{base_url}/rest/workspaces",
            headers={'Accept': 'application/json'},
            timeout=15,
            verify=False
        )
        response.raise_for_status()
        data = response.json()
        workspaces = (data.get('workspaces') or {}).get('workspace') or []
        return [w.get('name') for w in workspaces if w.get('name')]

    def list_datastores(self, workspace, config_loader_instance):
        """RF01 - lista os datastores de um workspace do GeoServer."""
        api_session = self.plugin.api_session
        if not api_session:
            raise Exception("Sessão da API não foi inicializada. Faça login primeiro.")

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

        response = api_session.get(
            f"{base_url}/rest/workspaces/{workspace}/datastores",
            headers={'Accept': 'application/json'},
            timeout=15,
            verify=False
        )
        response.raise_for_status()
        data = response.json()
        datastores = (data.get('dataStores') or {}).get('dataStore') or []
        return [d.get('name') for d in datastores if d.get('name')]

    def list_featuretypes(self, workspace, datastore, config_loader_instance):
        """Lista as tabelas visíveis nesse datastore (list=all - inclui as ainda não
        publicadas), igual a tela 'Publicar'/'Publicar novamente' do próprio GeoServer.
        Usado pra confirmar, ANTES do usuário clicar em publicar, que a tabela da camada
        ativa do QGIS realmente existe nesse workspace/datastore - evita o 400 'no
        attributes were specified' que acontece quando o Schema configurado no datastore
        é diferente do schema onde a tabela vive de verdade no banco."""
        api_session = self.plugin.api_session
        if not api_session:
            raise Exception("Sessão da API não foi inicializada. Faça login primeiro.")

        base_url = config_loader_instance.get_geoserver_url().rstrip('/')
        if not base_url:
            raise ValueError("A URL do GeoServer não está definida corretamente no config.json.")

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
                                      config_loader_instance, title=None, abstract=None, keywords=None):
        """RF02 - registro lógico: expõe uma tabela PostGIS já existente num datastore do
        GeoServer como FeatureType, sem tráfego de dados espaciais. 'name'/'nativeName'
        seguem a sanitização RF04; 'title' é livre (sem essas regras); 'abstract' e
        'keywords', quando fornecidos, vêm do metadado MGB já salvo pra camada."""
        api_session = self.plugin.api_session
        if not api_session:
            raise Exception("Sessão da API não foi inicializada. Faça login primeiro.")

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

    @staticmethod
    def translate_gs_error(status_code, text):
        """Traduz erros comuns da REST API do GeoServer (RN02)."""
        lower_text = (text or '').lower()
        if status_code == 403:
            return 'Acesso Negado — você não possui permissão de escrita neste Workspace.'
        if status_code == 404:
            return 'Workspace ou Datastore não encontrado.'
        if 'already exists' in lower_text:
            return 'Já existe uma camada com esse nome neste datastore.'
        if 'no attributes were specified' in lower_text:
            return (
                'O GeoServer não encontrou colunas para esta tabela no datastore selecionado. '
                'Causas mais comuns: (1) o Schema configurado nas Connection Parameters do '
                'datastore no GeoServer é diferente do schema onde a tabela vive no banco '
                '(veja o "schema.table" mostrado no card da camada), ou (2) a tabela não tem '
                'chave primária (obrigatória para publicação).'
            )
        return (text or f'Erro inesperado do GeoServer (status {status_code}).')[:400]

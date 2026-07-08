import json
import requests
import traceback
from qgis.PyQt import QtWidgets

class MetadataService:
    """
    Serviço que abstrai a comunicação com o GeoNetwork (API REST).
    """
    def __init__(self, plugin):
        self.plugin = plugin

    def push_to_geonetwork(self, xml_payload, config_loader_instance, uuid_processing='NOTHING'):
        """
        Publica um XML no GeoNetwork e retorna o UUID resultante ou lança exceção.
        uuid_processing: valores do enum GN `MEFLib$UuidAction` — 'NOTHING' (rejeita se o
        UUID já existir, padrão do GN), 'OVERWRITE' (sobrescreve o metadado existente com o
        mesmo UUID) ou 'GENERATEUUID' (ignora o UUID do XML e cria um registro novo).
        """
        api_session = self.plugin.api_session
        if not api_session:
            raise Exception("Sessão da API não foi inicializada. Faça login primeiro.")

        gn_urls = config_loader_instance.get_geonetwork_url()
        geonetwork_api_url = gn_urls.get('records_url')
        geonetwork_catalog_url = gn_urls.get('catalog_url')

        if not geonetwork_api_url or not geonetwork_catalog_url:
            raise ValueError("As URLs do GeoNetwork não estão definidas corretamente no config.json.")

        # Obtendo CSRF (XSRF-TOKEN) acessando a página inicial
        api_session.get(geonetwork_catalog_url, verify=False)

        csrf_token = None
        for cookie in api_session.cookies:
            if cookie.name == 'XSRF-TOKEN' and 'geonetwork' in cookie.path:
                csrf_token = cookie.value
                break

        headers = {
            'Content-Type': 'application/xml',
            'Accept': 'application/json'
        }
        if csrf_token:
            headers['X-XSRF-TOKEN'] = csrf_token

        response = api_session.put(
            geonetwork_api_url,
            data=xml_payload.encode('utf-8'),
            headers=headers,
            params={'publishToAll': 'false', 'uuidProcessing': uuid_processing}
        )
        
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise Exception(self.translate_http_error(response.text or str(response.status_code)))

        if response.status_code in [200, 201]:
            uuid_return = "N/A"
            try:
                response_data = response.json()
                # O campo 'uuid' na raiz da resposta é o id do job de processamento (SimpleMetadataProcessingReport),
                # não o uuid do metadado. O uuid real do registro fica dentro de 'metadataInfos'
                # (mapa id-interno -> lista de infos), ex.: {'348': [{'uuid': '...', 'message': '...'}]}.
                for entries in (response_data.get('metadataInfos') or {}).values():
                    if entries:
                        uuid_return = entries[0].get('uuid', 'N/A')
                        break
            except json.JSONDecodeError:
                pass
            return uuid_return
        else:
            raise Exception(f"Status inesperado: {response.status_code}")

    def fetch_from_geonetwork(self, uuid, config_loader_instance):
        """
        Busca o XML completo de um registro do GN por uuid e retorna já convertido
        pra dict (mesmo formato usado por load_layer_metadata/import_xml_file).
        Retorna None se o registro não existir. Funciona sem login pra registros públicos
        (sessão anônima) — GN só rejeita (401/403) se o registro exigir autenticação.
        """
        api_session = self.plugin.api_session or requests.Session()

        records_url = config_loader_instance.get_geonetwork_url().get('records_url')
        if not records_url:
            raise ValueError("A URL do GeoNetwork não está definida corretamente no config.json.")

        response = api_session.get(
            f"{records_url}/{uuid}/formatters/xml",
            timeout=15,
            verify=False
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()

        from .xml_parser import parse_xml_to_dict
        return parse_xml_to_dict(response.text, is_string=True)

    def translate_http_error(self, error_text):
        """Traduz mensagens comuns do GeoNetwork"""
        lower_error = error_text.lower()
        translations = {
            "authentication failed": "Falha na autenticação.",
            "unauthorized": "Acesso não autorizado.",
            "forbidden": "Você não tem privilégios de revisor.",
            "invalid credentials": "Credenciais inválidas.",
            "validation failed": "Falha na validação do servidor.",
            "already exist": "Já existe um metadado com este UUID no catálogo. Ao publicar novamente, escolha \"Sobrescrever\" ou \"Gerar UUID\" na tela de confirmação.",
            "nullpointerexception": "Erro interno do servidor.",
        }
        for key, translation in translations.items():
            if key in lower_error:
                return translation
        return error_text[:400]

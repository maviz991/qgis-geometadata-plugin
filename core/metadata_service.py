import json
import requests
import traceback
from qgis.PyQt import QtWidgets

class MetadataService:
    """
    Serviço que abstrai a comunicação com o GeoNetwork (API REST).
    """
    def __init__(self, api_session):
        self.api_session = api_session

    def push_to_geonetwork(self, xml_payload, config_loader_instance):
        """
        Publica um XML no GeoNetwork e retorna o UUID resultante ou lança exceção.
        """
        if not self.api_session:
            raise Exception("Sessão da API não foi inicializada. Faça login primeiro.")

        gn_urls = config_loader_instance.get_geonetwork_url() 
        geonetwork_api_url = gn_urls.get('records_url')
        geonetwork_catalog_url = gn_urls.get('catalog_url')

        if not geonetwork_api_url or not geonetwork_catalog_url:
            raise ValueError("As URLs do GeoNetwork não estão definidas corretamente no config.json.")

        # Obtendo CSRF (XSRF-TOKEN) acessando a página inicial
        self.api_session.get(geonetwork_catalog_url, verify=False)
        
        csrf_token = None
        for cookie in self.api_session.cookies:
            if cookie.name == 'XSRF-TOKEN' and 'geonetwork' in cookie.path:
                csrf_token = cookie.value
                break
                
        headers = {
            'Content-Type': 'application/xml',
            'Accept': 'application/json'
        }
        if csrf_token:
            headers['X-XSRF-TOKEN'] = csrf_token

        # O publishToAll falso é usado de default aqui.
        response = self.api_session.put(
            geonetwork_api_url,
            data=xml_payload.encode('utf-8'),
            headers=headers,
            params={'publishToAll': 'false'}
        )
        
        response.raise_for_status()

        if response.status_code in [200, 201]:
            uuid_return = "N/A"
            try:
                response_data = response.json()
                uuid_return = response_data.get('@uuid', response_data.get('uuid', 'N/A'))
            except json.JSONDecodeError:
                pass
            return uuid_return
        else:
            raise Exception(f"Status inesperado: {response.status_code}")

    def translate_http_error(self, error_text):
        """Traduz mensagens comuns do GeoNetwork"""
        lower_error = error_text.lower()
        translations = {
            "authentication failed": "Falha na autenticação.",
            "unauthorized": "Acesso não autorizado.",
            "forbidden": "Você não tem privilégios de revisor.",
            "invalid credentials": "Credenciais inválidas.",
            "validation failed": "Falha na validação do servidor.",
            "already exists": "Já existe.",
            "nullpointerexception": "Erro interno do servidor.",
        }
        for key, translation in translations.items():
            if key in lower_error:
                return translation
        return error_text[:400]

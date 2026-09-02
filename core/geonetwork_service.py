import json
import time
import requests
import traceback
from qgis.PyQt import QtWidgets

from .http_lock import HTTP_SESSION_LOCK

class GeoNetworkService:
    """
    Serviço que abstrai a comunicação com o GeoNetwork (API REST).
    """
    _FETCH_CACHE_TTL = 5  # segundos - ver fetch_from_geonetwork

    def __init__(self, plugin):
        self.plugin = plugin
        self._fetch_cache = {}  # uuid -> (timestamp, result)

    def push_to_geonetwork(self, xml_payload, config_loader_instance, uuid_processing='NOTHING'):
        """
        Publica um XML no GeoNetwork e retorna o UUID resultante ou lança exceção.
        uuid_processing: valores do enum GN `MEFLib$UuidAction` - 'NOTHING' (rejeita se o
        UUID já existir, padrão do GN), 'OVERWRITE' (sobrescreve o metadado existente com o
        mesmo UUID) ou 'GENERATEUUID' (ignora o UUID do XML e cria um registro novo).
        """
        api_session = self.plugin.api_session
        if not api_session:
            raise Exception("Sessão não foi inicializada. Faça login primeiro.")

        gn_urls = config_loader_instance.get_geonetwork_url()
        geonetwork_api_url = gn_urls.get('records_url')
        geonetwork_catalog_url = gn_urls.get('catalog_url')

        if not geonetwork_api_url or not geonetwork_catalog_url:
            raise ValueError("As URLs do GeoNetwork não estão definidas corretamente no config.json.")

        # Obtendo CSRF (XSRF-TOKEN) acessando a página inicial - warm-up + leitura dos
        # cookies num lock só (mesmo motivo do fetch_from_geonetwork: outra QThread pode
        # estar mutando api_session.cookies ao mesmo tempo, ver core/http_lock.py).
        csrf_token = None
        with HTTP_SESSION_LOCK:
            api_session.get(geonetwork_catalog_url, verify=False)
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

        with HTTP_SESSION_LOCK:
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
        (sessão anônima) - GN só rejeita (401/403) se o registro exigir autenticação.

        Cacheia o resultado por alguns segundos (_FETCH_CACHE_TTL) - não é um cache de
        dados "de verdade" (o registro pode mudar no Geohab a qualquer momento), só o
        suficiente pra cobrir chamadas que pedem o MESMO uuid quase ao mesmo tempo: abrir o
        editor de metadados dispara tanto check_gn_sync (GeoNetworkBridge) quanto
        GeoServerBridge._load_layer_metadata, e as duas buscam esse registro de forma
        independente - sem esse cache, cada abertura do painel batia duas vezes no Geohab
        (rede síncrona na UI thread), sendo a segunda chamada sempre redundante.
        """
        cached = self._fetch_cache.get(uuid)
        if cached and (time.time() - cached[0]) < self._FETCH_CACHE_TTL:
            return cached[1]

        api_session = self.plugin.api_session or requests.Session()

        gn_urls = config_loader_instance.get_geonetwork_url()
        records_url = gn_urls.get('records_url')
        catalog_url = gn_urls.get('catalog_url')
        if not records_url:
            raise ValueError("A URL do GeoNetwork não está definida corretamente no config.json.")

        # Mesmo "aquecimento" de sessão feito em push_to_geonetwork: sem essa primeira
        # visita ao catálogo, o GN nunca estabelece sua sessão interna (JSESSIONID/
        # XSRF-TOKEN) a partir da credencial do gateway (Basic Auth ou Bearer SSO), e
        # rejeita com 403 registros que exigem autenticação mesmo com token válido.
        # Tudo dentro do lock (inclusive a leitura de api_session.cookies) - essa sessão é
        # compartilhada com GeoServerService após login local (ver core/http_lock.py) e
        # outra QThread pode estar mutando os cookies ao mesmo tempo.
        with HTTP_SESSION_LOCK:
            if catalog_url and not any(
                c.name == 'XSRF-TOKEN' and 'geonetwork' in c.path for c in api_session.cookies
            ):
                api_session.get(catalog_url, verify=False)

            response = api_session.get(
                f"{records_url}/{uuid}/formatters/xml",
                timeout=15,
                verify=False
            )
        if response.status_code == 404:
            self._fetch_cache[uuid] = (time.time(), None)
            return None
        response.raise_for_status()

        from .xml_parser import parse_xml_to_dict
        result = parse_xml_to_dict(response.text, is_string=True)
        self._fetch_cache[uuid] = (time.time(), result)
        return result

    def translate_http_error(self, error_text):
        """Traduz mensagens comuns do GeoNetwork"""
        lower_error = error_text.lower()
        translations = {
            "authentication failed": "[GN-401] Falha na autenticação.",
            "unauthorized": "[GN-401] Acesso não autorizado.",
            "forbidden": "[GN-403] Você não tem privilégios de revisor.",
            "invalid credentials": "[GN-401] Credenciais inválidas.",
            "validation failed": "[GN-422] Falha na validação do servidor.",
            "already exist": "[GN-409] Já existe um metadado com este UUID no catálogo. Ao publicar novamente, escolha \"Sobrescrever\" ou \"Gerar UUID\" na tela de confirmação.",
            "nullpointerexception": "[GN-500] Erro interno do servidor.",
        }
        for key, translation in translations.items():
            if key in lower_error:
                return translation
        return f"[GN-000] {error_text[:400]}"

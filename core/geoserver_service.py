import re
import unicodedata


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

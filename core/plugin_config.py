# plugin_config.py
import json
import os

class PluginConfig:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PluginConfig, cls).__new__(cls, *args, **kwargs)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        self.config = {}
        config_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"CRITICAL: Não foi possível carregar o arquivo de configuração: {e}")
            self.config['geonetwork_url'] = ""
            self.config['geoserver_url'] = ""

    def get_geonetwork_url(self):
        """ Retorna um dicionário com as URLs detalhadas do GeoNetwork. """
        base_url = self.config.get("geonetwork_url", "")
        return {
            "records_url": f"{base_url}/srv/api/records",
            "catalog_url": f"{base_url}/srv/eng/catalog.search"
        }
    
    def get_geonetwork_edit(self):
        """ Retorna um dicionário com as URLs detalhadas do GeoNetwork. """
        base_url = self.config.get("geonetwork_url", "")
        return f"{base_url}/srv/por/catalog.edit#/board"
            
    
    def get_metadata_view_url(self, uuid):
        """ Constrói a URL DINÂMICA para ver um metadado específico. """
        base_url = self.get_geonetwork_base_url()
        if not uuid or uuid == "N/A":
            return base_url
        return f"{base_url}/srv/por/catalog.search#/metadata/{uuid}"
    
    # --- NOVO MÉTODO ADICIONADO ---
    def get_geonetwork_base_url(self):
        """ Retorna apenas a URL base do GeoNetwork. """
        return self.config.get("geonetwork_url", "")

    def get_geoserver_url(self):
        return self.config.get("geoserver_url", "")

    def get_entra_id_config(self):
        """
        Retorna as configurações do Microsoft Entra ID.
        Retorna None se o bloco 'entra_id' não existir no config.
        """
        return self.config.get("entra_id", None)

    def has_entra_id_configured(self) -> bool:
        """
        Retorna True somente se client_id e tenant_id estiverem preenchidos
        (i.e., não são os valores placeholder 'AGUARDANDO_TI').
        """
        entra = self.get_entra_id_config()
        if not entra:
            return False
        client_id = entra.get("client_id", "")
        tenant_id = entra.get("tenant_id", "")
        placeholder = "AGUARDANDO_TI"
        return bool(client_id) and bool(tenant_id) and \
               client_id != placeholder and tenant_id != placeholder

# Cria uma instância única que pode ser importada em todo o plugin
config_loader = PluginConfig()
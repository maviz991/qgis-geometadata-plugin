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
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"CRITICAL: Não foi possível carregar o arquivo de configuração: {e}")
            # Você pode definir valores padrão aqui como fallback
            self.config['geonetwork_url'] = ""
            self.config['geoserver_url'] = ""

    def get_geonetwork_url(self):
        base_url = self.config.get("geonetwork_url", "")
        return {
            "records_url": f"{base_url}/srv/api/records",
            "catalog_url": f"{base_url}/srv/eng/catalog.search"
        }

    def get_geoserver_url(self):
        return self.config.get("geoserver_url", "")

# Cria uma instância única que pode ser importada em todo o plugin
config_loader = PluginConfig()
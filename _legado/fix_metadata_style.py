import re

# 1. Update _GsUpdateMetadataWorker in ui/geoserver_workers.py
with open("ui/geoserver_workers.py", "r", encoding="utf-8") as f:
    workers_content = f.read()

# Replace constructor and run logic for _GsUpdateMetadataWorker
worker_pattern = r"(class _GsUpdateMetadataWorker\(QThread\):\n\s+done = pyqtSignal\(bool, str\)\n\n\s+def __init__\(self, geoserver_service, workspace, datastore, published_name, title, abstract, keywords, )(style_json)(, config_loader_instance\):).*?(self\.done\.emit\(True, 'Metadados atualizados com sucesso\.'\)\n\s+except Exception as exc:\n\s+self\.done\.emit\(False, str\(exc\)\))"

new_worker_logic = r"""\1style_task\3
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

    def run(self):
        try:
            self._service.update_published_featuretype(
                self._workspace, self._datastore, self._published_name, self._config,
                title=self._title, abstract=self._abstract, keywords=self._keywords
            )
            
            if self._style_task:
                try:
                    self._service.apply_style(self._workspace, self._published_name, self._style_task, self._config)
                except Exception as exc:
                    self.done.emit(False, f'Metadados atualizados, mas falha ao aplicar estilo: {str(exc)}')
                    return

            \4"""
workers_content = re.sub(worker_pattern, new_worker_logic, workers_content, flags=re.DOTALL)

with open("ui/geoserver_workers.py", "w", encoding="utf-8") as f:
    f.write(workers_content)

# 2. Update update_layer_metadata in ui/geoserver_bridge.py
with open("ui/geoserver_bridge.py", "r", encoding="utf-8") as f:
    bridge_content = f.read()

bridge_pattern = r"(def update_layer_metadata\(self, workspace, datastore, published_name, title, abstract, keywords, style_json=''\):\n\s+geoserver_service = getattr\(self\._dialog, 'geoserver_service', None\)\n\s+if not geoserver_service:\n\s+self\.gs_metadata_updated\.emit\(False, 'Serviço GeoServer não inicializado\.'\)\n\s+return\n\s+)(from \.\.core\.plugin_config import config_loader\n\s+from \.geoserver_workers import _GsUpdateMetadataWorker\n\s+self\._update_metadata_worker = _GsUpdateMetadataWorker\(\n\s+geoserver_service, workspace, datastore, published_name, title, abstract, keywords, )(style_json)(, config_loader\n\s+\)\n\s+self\._update_metadata_worker\.done\.connect\(self\._on_standard_metadata_updated\)\n\s+self\._update_metadata_worker\.start\(\))"

new_bridge_logic = r"""\1style_task = None
        if style_json:
            import json
            try:
                style_cfg = json.loads(style_json)
                if style_cfg.get('source') not in ('', 'none') and style_cfg.get('type') != 'sys_keep':
                    # pass None for layer since there's no active layer in this flow
                    style_task, error = self._prepare_style_task(style_cfg, None, workspace)
                    if error:
                        self.gs_metadata_updated.emit(False, error)
                        return
            except Exception as e:
                self.gs_metadata_updated.emit(False, f"Erro ao processar estilo: {e}")
                return
        
        \2style_task\4"""

bridge_content = re.sub(bridge_pattern, new_bridge_logic, bridge_content, flags=re.DOTALL)

with open("ui/geoserver_bridge.py", "w", encoding="utf-8") as f:
    f.write(bridge_content)

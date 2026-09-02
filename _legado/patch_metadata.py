import re

# 1. Update geoserver_bridge.py
with open("ui/geoserver_bridge.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add signal
if "gs_metadata_updated =" not in content:
    content = content.replace("    gs_publish_done = pyqtSignal(bool, str, str, str, str)",
                              "    gs_publish_done = pyqtSignal(bool, str, str, str, str)\n    gs_metadata_updated = pyqtSignal(bool, str)")

# Add update_layer_metadata method
if "def update_layer_metadata(" not in content:
    new_methods = """
    @pyqtSlot(str, str, str, str, str, 'QVariant', str)
    def update_layer_metadata(self, workspace, datastore, published_name, title, abstract, keywords, style_json=''):
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_metadata_updated.emit(False, 'Serviço GeoServer não inicializado.')
            return
        
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsUpdateMetadataWorker
        self._update_metadata_worker = _GsUpdateMetadataWorker(
            geoserver_service, workspace, datastore, published_name, title, abstract, keywords, style_json, config_loader
        )
        self._update_metadata_worker.done.connect(self._on_standard_metadata_updated)
        self._update_metadata_worker.start()

    @pyqtSlot(bool, str)
    def _on_standard_metadata_updated(self, ok, message):
        self.gs_metadata_updated.emit(ok, message)
"""
    # Append to end of class (before module-level code if any, or just end of file)
    content += new_methods

with open("ui/geoserver_bridge.py", "w", encoding="utf-8") as f:
    f.write(content)

# 2. Update geoserver.js
with open("ui/templates/js/geoserver.js", "r", encoding="utf-8") as f:
    js_content = f.read()

if "gsBridge.gs_metadata_updated.connect" not in js_content:
    js_content = js_content.replace("    gsBridge.gs_publish_done.connect(function (success, message, published_name, wmsUrl, wfsUrl) {",
                                    "    gsBridge.gs_metadata_updated.connect(function (success, message) {\n        _hideActionLoading();\n        if (success) {\n            _gsForceLiveRecheck();\n            Modal.alert(message, 'Atualizado', 'success');\n        } else {\n            Modal.alert(message, 'Erro', 'error');\n        }\n    });\n\n    gsBridge.gs_publish_done.connect(function (success, message, published_name, wmsUrl, wfsUrl) {")

if "Deseja atualizar os metadados" not in js_content:
    replacement = """
    if (!_gsLayerInfo || !_gsLayerInfo.publishable) {
        var wmsName = (window._gnPullWmsData && window._gnPullWmsData.geoserver_layer_name) || '';
        var d2 = _gsCollectFormState();
        if (wmsName && d2.workspace && d2.datastore && d2.published_name) {
            Modal.confirm(
                'Nenhuma camada ativa no QGIS. Como o destino está preenchido, deseja apenas ATUALIZAR os metadados ' +
                '(Título/Resumo/Palavras-chave) e Estilo dessa camada no GeoServer?',
                function () {
                    _showActionLoading('Atualizando metadados no GeoServer...');
                    var style = _gsCollectStyleConfig();
                    gsBridge.update_layer_metadata(
                        d2.workspace, d2.datastore, d2.published_name,
                        d2.title, d2.abstract, d2.keywords, style ? JSON.stringify(style) : ''
                    );
                },
                'Atualizar Metadados'
            );
        } else {
            Modal.alert((_gsLayerInfo && _gsLayerInfo.reason) || 'Nenhuma camada publicável ativa no QGIS.', 'Aviso', 'warning');
        }
        return;
    }
"""
    js_content = re.sub(r"    if \(!_gsLayerInfo \|\| !_gsLayerInfo\.publishable\) \{\s+Modal\.alert\(\(_gsLayerInfo && _gsLayerInfo\.reason\) \|\| 'Nenhuma camada publicável ativa no QGIS\.', 'Aviso', 'warning'\);\s+return;\s+\}", replacement, js_content)

with open("ui/templates/js/geoserver.js", "w", encoding="utf-8") as f:
    f.write(js_content)

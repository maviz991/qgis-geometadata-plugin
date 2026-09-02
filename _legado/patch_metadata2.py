import re

with open("ui/templates/js/geoserver.js", "r", encoding="utf-8") as f:
    js_content = f.read()

# Add gs_metadata_updated signal connection
target_str = "    gsBridge.gs_publish_done.connect(function (success, message, publishedName, wmsUrl, wfsUrl) {"
if "gsBridge.gs_metadata_updated.connect" not in js_content and target_str in js_content:
    replacement_str = """    gsBridge.gs_metadata_updated.connect(function (success, message) {
        _hideActionLoading();
        if (success) {
            _gsForceLiveRecheck();
            Modal.alert(message, 'Atualizado', 'success');
        } else {
            Modal.alert(message, 'Erro', 'error');
        }
    });

    gsBridge.gs_publish_done.connect(function (success, message, publishedName, wmsUrl, wfsUrl) {"""
    js_content = js_content.replace(target_str, replacement_str)

# Modify confirmGsPublish function
if "Deseja atualizar os metadados" not in js_content:
    # We will use regex to find the start of confirmGsPublish
    pattern = r"(function confirmGsPublish\(\) \{\s+)(if \(!_gsLayerInfo \|\| !_gsLayerInfo\.publishable\) \{\s+Modal\.alert\(\(_gsLayerInfo && _gsLayerInfo\.reason\) \|\| 'Nenhuma camada publicável ativa no QGIS\.', 'Aviso', 'warning'\);\s+return;\s+\})"
    
    replacement = r"""\1if (!_gsLayerInfo || !_gsLayerInfo.publishable) {
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
    }"""
    
    js_content = re.sub(pattern, replacement, js_content)

with open("ui/templates/js/geoserver.js", "w", encoding="utf-8") as f:
    f.write(js_content)

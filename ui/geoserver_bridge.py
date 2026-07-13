# -*- coding: utf-8 -*-
"""
geoserver_bridge.py — GeoMetadata Plugin
=====================================
Ponte de comunicação específica do GeoServer (busca de camadas hoje;
publicação de camadas/workspaces nas próximas fases — ver requisitos_v2.md).
Exposto ao JS via QWebChannel como 'gsBridge'.
"""

from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot


class GeoServerBridge(QObject):
    """
    Ponte GeoServer para o diálogo do plugin.
    Sinais JS -> Python e Python -> JS específicos do GeoServer.
    """

    gs_workspaces_ready = pyqtSignal(list, str)  # workspaces, error

    # Cache de camadas do GeoServer (carregado uma vez por sessão)
    _geoserver_layers_cache = None

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._workspaces_worker = None

    @pyqtSlot()
    def list_workspaces(self):
        """RF01 — lista os workspaces do GeoServer em background (QThread, RNF02) e
        emite gs_workspaces_ready(workspaces, error) quando terminar."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_workspaces_ready.emit([], 'Serviço GeoServer não inicializado.')
            return
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsWorkspacesWorker
        self._workspaces_worker = _GsWorkspacesWorker(geoserver_service, config_loader)
        self._workspaces_worker.done.connect(self.gs_workspaces_ready.emit)
        self._workspaces_worker.start()

    @pyqtSlot(str, result='QVariant')
    def search_geoserver(self, query: str):
        """Busca camadas públicas no GeoServer via WMS GetCapabilities (sem autenticação).
        Usado hoje pelo editor GN (aba 'Recursos associados') pra linkar uma camada
        existente ao metadado — é o gsBridge quem sabe falar com o GeoServer."""
        try:
            import ssl
            import urllib.request
            import xml.etree.ElementTree as ET
            from ..core.plugin_config import config_loader

            base_url = config_loader.get_geoserver_url().rstrip('/')
            if not base_url:
                print("GeoMetadata [search_geoserver]: geoserver_url não configurado.")
                return []

            is_logged = getattr(getattr(self._dialog, 'plugin', None), 'api_session', None) is not None

            if GeoServerBridge._geoserver_layers_cache is None:
                caps_url = f"{base_url}/wms?service=WMS&version=1.3.0&request=GetCapabilities"
                print(f"GeoMetadata [search_geoserver]: carregando capabilities de {caps_url}")

                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode    = ssl.CERT_NONE

                req = urllib.request.Request(caps_url, headers={'User-Agent': 'GeoMetadataPlugin/1.0'})
                with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                    content = resp.read()

                print(f"GeoMetadata [search_geoserver]: {len(content)} bytes recebidos.")

                root = ET.fromstring(content)
                all_layers = []

                for layer_el in root.iter():
                    tag_local = layer_el.tag.split('}')[-1] if '}' in layer_el.tag else layer_el.tag
                    if tag_local != 'Layer':
                        continue
                    name_el = title_el = None
                    for child in layer_el:
                        ct = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        if ct == 'Name'  and name_el  is None: name_el  = child
                        if ct == 'Title' and title_el is None: title_el = child
                    name  = (name_el.text  or '').strip() if name_el  is not None else ''
                    title = (title_el.text or '').strip() if title_el is not None else ''
                    if not name or ':' not in name:
                        continue
                    workspace = name.split(':', 1)[0]
                    all_layers.append({
                        'name':      name,
                        'workspace': workspace,
                        'title':     title or name,
                        'wms_url':   f"{base_url}/{workspace}/wms?service=WMS",
                        'wfs_url':   f"{base_url}/{workspace}/wfs?service=WFS",
                    })

                GeoServerBridge._geoserver_layers_cache = all_layers
                print(f"GeoMetadata [search_geoserver]: {len(all_layers)} camadas indexadas.")

            q = query.lower().strip()
            cache = GeoServerBridge._geoserver_layers_cache
            results = [l for l in cache if q in l['name'].lower() or q in l['title'].lower()][:25]

            for r in results:
                r['wfs_available'] = is_logged

            return results

        except Exception as e:
            import traceback
            print(f"GeoMetadata [search_geoserver] ERRO: {e}")
            traceback.print_exc()
            return []

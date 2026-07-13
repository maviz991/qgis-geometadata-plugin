# -*- coding: utf-8 -*-
"""
geoserver_bridge.py - GeoMetadata Plugin
=====================================
Ponte de comunicação específica do GeoServer (busca de camadas hoje;
publicação de camadas/workspaces nas próximas fases - ver requisitos_v2.md).
Exposto ao JS via QWebChannel como 'gsBridge'.
"""

from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot


class GeoServerBridge(QObject):
    """
    Ponte GeoServer para o diálogo do plugin.
    Sinais JS -> Python e Python -> JS específicos do GeoServer.
    """

    gs_workspaces_ready = pyqtSignal(list, str)  # workspaces, error
    gs_datastores_ready = pyqtSignal(list, str)  # datastores, error
    gs_publish_done = pyqtSignal(bool, str, str, str, str)  # sucesso, mensagem, nome_publicado, wms_url, wfs_url

    # Cache de camadas do GeoServer (carregado uma vez por sessão)
    _geoserver_layers_cache = None

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._workspaces_worker = None
        self._datastores_worker = None
        self._publish_worker = None

    @pyqtSlot()
    def list_workspaces(self):
        """RF01 - lista os workspaces do GeoServer em background (QThread, RNF02) e
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

    @pyqtSlot(str)
    def list_datastores(self, workspace):
        """RF01 - lista os datastores de um workspace do GeoServer em background e
        emite gs_datastores_ready(datastores, error) quando terminar."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_datastores_ready.emit([], 'Serviço GeoServer não inicializado.')
            return
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsDatastoresWorker
        self._datastores_worker = _GsDatastoresWorker(geoserver_service, workspace, config_loader)
        self._datastores_worker.done.connect(self.gs_datastores_ready.emit)
        self._datastores_worker.start()

    def _active_layer(self):
        plugin = getattr(self._dialog, 'plugin', None)
        iface = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
        return iface.activeLayer() if iface else None

    def _load_layer_metadata(self, layer):
        """Busca o metadado MGB da camada pra pré-preencher o Título e mandar Resumo/
        Palavras-chave junto na publicação no GeoServer. Tenta o local (DB/sidecar)
        primeiro pra pegar o metadata_uuid; se a camada já foi publicada no GeoNetwork,
        busca o XML de lá também (fonte mais fresca/confiável - a cópia local pode estar
        desatualizada ou incompleta) e usa esse como resultado final quando disponível."""
        try:
            ps = getattr(self._dialog, 'persistence_service', None)
            local = None
            if ps and layer:
                xml_content = ps.load(layer)
                if xml_content:
                    from ..core import xml_parser
                    local = xml_parser.parse_xml_to_dict(xml_content, is_string=True)

            uuid = (local or {}).get('metadata_uuid')
            geonetwork_service = getattr(self._dialog, 'geonetwork_service', None)
            if uuid and geonetwork_service:
                from ..core.plugin_config import config_loader
                try:
                    remote = geonetwork_service.fetch_from_geonetwork(uuid, config_loader)
                    if remote:
                        return remote
                except Exception as exc:
                    print(f"GeoMetadata [_load_layer_metadata] fallback GeoNetwork falhou: {exc}")

            return local
        except Exception as exc:
            print(f"GeoMetadata [_load_layer_metadata]: {exc}")
            return None

    @pyqtSlot(result='QVariant')
    def get_active_layer_publish_info(self):
        """Diz ao JS se a camada ativa do QGIS pode ser publicada no GeoServer (RF02) -
        só camadas PostGIS são suportadas, ver GeoServerService.get_active_layer_publish_info.
        Quando publicável, inclui 'title'/'abstract'/'keywords' pré-preenchidos a partir do
        metadado MGB salvo (se existir) - calculados aqui uma única vez e devolvidos pro JS,
        que manda esses mesmos valores de volta explicitamente em publish_layer() (em vez de
        buscar de novo lá, o que já causou inconsistência entre as duas buscas)."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            return {'publishable': False, 'reason': 'Serviço GeoServer não inicializado.'}
        try:
            layer = self._active_layer()
            info = geoserver_service.get_active_layer_publish_info(layer)
            if info.get('publishable'):
                md = self._load_layer_metadata(layer) or {}
                info['title'] = md.get('title') or info.get('name') or ''
                info['abstract'] = md.get('abstract') or ''
                info['keywords'] = md.get('MD_Keywords') or []
            return info
        except Exception as exc:
            return {'publishable': False, 'reason': str(exc)}

    @pyqtSlot(str, result=str)
    def sanitize_layer_name(self, name):
        """RF04 - preview síncrono do nome sanitizado (só regex, sem I/O de rede)."""
        from ..core.geoserver_service import GeoServerService
        return GeoServerService.sanitize_layer_name(name)

    @pyqtSlot(str, str, str, str, str, 'QVariant')
    def publish_layer(self, workspace, datastore, published_name, title, abstract, keywords):
        """RF02 - publica (registra) a camada ativa do QGIS como FeatureType no
        workspace/datastore escolhidos. Reconsulta a camada ativa aqui (não confia em
        estado antigo vindo do JS) e dispara o worker em background (RNF02). title/
        abstract/keywords vêm explicitamente do JS (o mesmo valor que get_active_layer_
        publish_info já tinha calculado e mostrado na tela) - 'name'/'nativeName' seguem
        a regra de sanitização (RF04), os demais são livres."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_publish_done.emit(False, 'Serviço GeoServer não inicializado.', published_name, '', '')
            return

        layer = self._active_layer()
        info = geoserver_service.get_active_layer_publish_info(layer)
        if not info.get('publishable'):
            self.gs_publish_done.emit(False, info.get('reason') or 'Camada não publicável.', published_name, '', '')
            return

        keywords = list(keywords) if keywords else []

        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsPublishWorker
        self._publish_worker = _GsPublishWorker(
            geoserver_service, workspace, datastore, info['table'], published_name,
            title or published_name, abstract, keywords, config_loader
        )
        self._publish_worker.done.connect(
            lambda success, message, name: self._on_publish_done(success, message, name, workspace, config_loader)
        )
        self._publish_worker.start()

    def _on_publish_done(self, success, message, published_name, workspace, config_loader_instance):
        """Além de repassar o resultado, calcula as URLs WMS/WFS da camada recém-publicada -
        usadas pelo JS (geonetwork.js) pra vincular automaticamente os dois em Distribuição
        e gerar a miniatura, sem o usuário ter que ir lá manualmente linkar de novo."""
        wms_url = wfs_url = ''
        if success:
            base_url = config_loader_instance.get_geoserver_url().rstrip('/')
            wms_url = f"{base_url}/{workspace}/wms?service=WMS"
            wfs_url = f"{base_url}/{workspace}/wfs?service=WFS"
        self.gs_publish_done.emit(success, message, published_name, wms_url, wfs_url)

    @pyqtSlot(str, result='QVariant')
    def search_geoserver(self, query: str):
        """Busca camadas públicas no GeoServer via WMS GetCapabilities (sem autenticação).
        Usado hoje pelo editor GN (aba 'Recursos associados') pra linkar uma camada
        existente ao metadado - é o gsBridge quem sabe falar com o GeoServer."""
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

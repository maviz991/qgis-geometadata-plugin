# -*- coding: utf-8 -*-
"""
main_bridge.py — GeoMetadata Plugin
=====================================
Ponte de comunicação para a interface principal em HTML.
Exposto ao JS via QWebChannel como 'bridge'.
"""

import os
from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot

class MainBridge(QObject):
    """
    Ponte principal para o diálogo do plugin.
    Sinais JS -> Python e Python -> JS.
    """

    # Sinais emitidos para o JS
    nav_changed   = pyqtSignal(str)       # Notifica mudança de painel
    auth_status   = pyqtSignal(bool, str) # (is_logged, username)
    form_data_req = pyqtSignal('QVariant') # Envia dados para preencher o form
    login_loading = pyqtSignal(str)       # Mensagem de carregamento durante auth
    login_error   = pyqtSignal(str)       # Erro de autenticação
    layer_changed = pyqtSignal(str)       # Nome da camada ativa mudou

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._form_manager = getattr(dialog, 'form_manager', None)
        self._sso_worker = None
        self._adm_worker = None
        try:
            plugin = getattr(dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(dialog, 'iface', None)
            if iface:
                iface.currentLayerChanged.connect(self._on_layer_changed)
        except Exception:
            pass

    def _on_layer_changed(self, layer):
        self.layer_changed.emit(layer.name() if layer else "")

    @pyqtSlot(result=str)
    def get_active_layer_name(self) -> str:
        """Retorna o nome da camada ativa no QGIS."""
        try:
            plugin = getattr(self._dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
            layer  = iface.activeLayer() if iface else None
            return layer.name() if layer else ""
        except Exception:
            return ""
        
    # --- Slots JS -> Python ---

    @pyqtSlot(str)
    def navigate(self, panel_id: str):
        """Muda o painel atual (home, editor, geoserver)."""
        print(f"GeoMetadata: Navegando para {panel_id}")
        self.nav_changed.emit(panel_id)

    @pyqtSlot('QVariant')
    def update_form_state(self, data):
        """
        Recebe dados do formulário HTML e atualiza o estado interno.
        Isso substitui o binding direto dos widgets PyQt.
        """
        if self._form_manager:
            # Aqui sincronizaremos os valores com o FormManager
            # por enquanto apenas logamos
            print(f"GeoMetadata: Atualizando estado do form com {len(data)} campos")
            # self._form_manager.update_from_dict(data)

    @pyqtSlot('QVariant')
    def save_metadata(self, form_data):
        """Salva o metadado (rascunho local). Recebe o dict do formulário HTML."""
        self._dialog.save_metadata(metadata_dict=form_data if isinstance(form_data, dict) else None)

    @pyqtSlot()
    def start_login(self):
        """Inicia autenticação SSO corporativa sem abrir diálogo Qt separado."""
        try:
            from ..core.env_checker import check_and_run_setup
            if not check_and_run_setup(parent=self._dialog):
                self.login_error.emit("Dependência MSAL não encontrada. Configure o ambiente primeiro.")
                return
            from ..core.plugin_config import config_loader
            from ..core.entra_auth_provider import EntraAuthProvider
            from .web_bridge import _SsoWorker
            entra_cfg = config_loader.get_entra_id_config()
            provider  = EntraAuthProvider(
                client_id=entra_cfg.get("client_id", ""),
                tenant_id=entra_cfg.get("tenant_id", ""),
                scopes=entra_cfg.get("scopes", ["User.Read"])
            )
            self.login_loading.emit("Aguardando autenticação no navegador...")
            self._sso_worker = _SsoWorker(provider)
            self._sso_worker.auth_success.connect(self._on_sso_success)
            self._sso_worker.auth_failed.connect(self._on_sso_failed)
            self._sso_worker.start()
        except Exception as e:
            self.login_error.emit(str(e))

    def _on_sso_success(self, provider):
        session = provider.get_session()
        username = provider.get_username() or "Usuário CDHU"
        self._dialog.plugin.api_session = session
        self._dialog.plugin.auth_username = username
        self._dialog.update_ui_for_login_status()

    def _on_sso_failed(self, msg):
        self.login_error.emit(msg)

    @pyqtSlot(str, str)
    def do_admin_login(self, user: str, password: str):
        """Login administrativo (usuário/senha GeoServer) sem abrir diálogo Qt separado."""
        try:
            from ..core.plugin_config import config_loader
            from .web_bridge import _AdminWorker
            geoserver_url = config_loader.get_geoserver_url()
            self.login_loading.emit("Verificando credenciais...")
            self._adm_worker = _AdminWorker(user, password, geoserver_url)
            self._adm_worker.login_success.connect(self._on_adm_success)
            self._adm_worker.login_failed.connect(self._on_adm_failed)
            self._adm_worker.start()
        except Exception as e:
            self.login_error.emit(str(e))

    def _on_adm_success(self, session, username):
        self._dialog.plugin.api_session = session
        self._dialog.plugin.auth_username = username
        self._dialog.update_ui_for_login_status()

    def _on_adm_failed(self, msg):
        self.login_error.emit(msg)

    @pyqtSlot()
    def logout(self):
        """Encerra a sessão do usuário."""
        self._dialog.plugin.api_session = None
        self._dialog.plugin.auth_username = None
        self._dialog.update_ui_for_login_status()

    @pyqtSlot('QVariant')
    def export_xml(self, form_data):
        """Exporta metadados para XML local. Recebe o dict do formulário HTML."""
        self._dialog.exportar_to_xml(metadata_dict=form_data if isinstance(form_data, dict) else None)

    @pyqtSlot('QVariant')
    def export_geohab(self, form_data):
        """Publica o metadado no GeoNetwork. Recebe o dict do formulário HTML."""
        self._dialog.exportar_to_geo(metadata_dict=form_data if isinstance(form_data, dict) else None)

    @pyqtSlot()
    def close_dialog(self):
        """Fecha o diálogo do plugin."""
        self._dialog.close()

    @pyqtSlot(result='QVariant')
    def get_initial_data(self):
        """Retorna dados iniciais para o painel Home e Editor."""
        is_logged = self._dialog.plugin.api_session is not None
        username = self._dialog.plugin.auth_username or "Visitante"
        return {
            "version": "3.0.0-beta",
            "user": username,
            "is_logged": is_logged
        }

    @pyqtSlot(result='QVariant')
    def get_layer_info(self):
        """Retorna SRC e extensão geográfica (WGS84) da camada ativa no QGIS."""
        try:
            from qgis.core import (QgsCoordinateTransform,
                                   QgsCoordinateReferenceSystem,
                                   QgsProject)
            plugin = getattr(self._dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
            layer  = iface.activeLayer() if iface else None
            if not layer:
                return None
            crs     = layer.crs()
            auth_id = crs.authid()
            desc    = crs.description()
            result  = {'code': auth_id, 'title': desc + ' (' + auth_id + ')'}
            extent  = layer.extent()
            if not extent.isEmpty():
                wgs84     = QgsCoordinateReferenceSystem('EPSG:4326')
                transform = QgsCoordinateTransform(crs, wgs84, QgsProject.instance())
                wgs_ext   = transform.transformBoundingBox(extent)
                result['north'] = round(wgs_ext.yMaximum(), 6)
                result['south'] = round(wgs_ext.yMinimum(), 6)
                result['east']  = round(wgs_ext.xMaximum(), 6)
                result['west']  = round(wgs_ext.xMinimum(), 6)
            return result
        except Exception:
            return None

    @pyqtSlot(str, result='QVariant')
    def search_contacts(self, query: str):
        """Busca contatos nos predefinidos locais que correspondem à query. Retorna lista para o JS."""
        predefinidos = getattr(self._dialog, 'contatos_predefinidos', {})
        q = query.lower().strip()
        results = []
        for key, data in predefinidos.items():
            if key == 'nenhum':
                continue
            org   = data.get('contact_organisationName', '')
            sigla = data.get('contact_individualName', '')
            email = data.get('contact_email', '')
            if not q or q in org.lower() or q in sigla.lower() or q in email.lower():
                results.append({
                    'sigla':    sigla,
                    'org':      org,
                    'email':    email,
                    'position': data.get('contact_positionName', ''),
                    'phone':    data.get('contact_phone', ''),
                    'address':  data.get('contact_deliveryPoint', ''),
                    'city':     data.get('contact_city', ''),
                    'state':    data.get('contact_administrativeArea', ''),
                    'zip':      data.get('contact_postalCode', ''),
                    'country':  data.get('contact_country', 'Brasil'),
                    'role':     data.get('contact_role', '')
                })
        return results

    # Cache de camadas do GeoServer (carregado uma vez por sessão)
    _geoserver_layers_cache = None

    @pyqtSlot(str, result='QVariant')
    def search_geoserver(self, query: str):
        """Busca camadas públicas no GeoServer via WMS GetCapabilities (sem autenticação)."""
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

            if MainBridge._geoserver_layers_cache is None:
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

                MainBridge._geoserver_layers_cache = all_layers
                print(f"GeoMetadata [search_geoserver]: {len(all_layers)} camadas indexadas.")

            q = query.lower().strip()
            cache = MainBridge._geoserver_layers_cache
            results = [l for l in cache if q in l['name'].lower() or q in l['title'].lower()][:25]

            for r in results:
                r['wfs_available'] = is_logged

            return results

        except Exception as e:
            import traceback
            print(f"GeoMetadata [search_geoserver] ERRO: {e}")
            traceback.print_exc()
            return []

    @pyqtSlot(str, result=str)
    def load_panel_html(self, panel_id: str) -> str:
        """Lê o HTML de um painel do disco e retorna como string para o JS."""
        panels_dir = os.path.join(os.path.dirname(__file__), "templates", "panels")
        panel_path = os.path.join(panels_dir, f"{panel_id}.html")
        try:
            with open(panel_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return f'<div style="padding:20px;color:red">Painel "{panel_id}" não encontrado.</div>'

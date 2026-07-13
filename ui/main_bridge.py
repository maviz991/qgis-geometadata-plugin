# -*- coding: utf-8 -*-
"""
main_bridge.py — GeoMetadata Plugin
=====================================
Ponte de comunicação genérica (app-shell) para a interface principal em HTML:
navegação, camadas do QGIS, login/logout, e utilidades sem domínio específico
(toast, abrir pasta no explorer). Exposto ao JS via QWebChannel como 'bridge'.

Lógica específica de GeoNetwork está em geonetwork_bridge.py ('gnBridge') e de
GeoServer em geoserver_bridge.py ('gsBridge').
"""

import os
from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot
from ..core.plugin_config import config_loader

class MainBridge(QObject):
    """
    Ponte principal (genérica) para o diálogo do plugin.
    Sinais JS -> Python e Python -> JS.
    """

    # Sinais emitidos para o JS
    nav_changed    = pyqtSignal(str)            # Notifica mudança de painel
    auth_status    = pyqtSignal(bool, str)      # (is_logged, username)
    form_data_req  = pyqtSignal('QVariant')     # Envia dados para preencher o form
    login_loading  = pyqtSignal(str)            # Mensagem de carregamento durante auth
    login_error    = pyqtSignal(str)            # Erro de autenticação
    layer_changed  = pyqtSignal(str)            # Nome da camada ativa mudou
    toast          = pyqtSignal(str, str, str)  # message, title, type

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

    @pyqtSlot(result='QVariant')
    def list_layers(self):
        """Retorna lista de camadas carregadas no projeto QGIS atual."""
        try:
            from qgis.core import QgsProject, QgsRasterLayer
            layers = QgsProject.instance().mapLayers().values()
            result = []
            for l in layers:
                t = 'raster' if isinstance(l, QgsRasterLayer) else 'vector'
                result.append({'id': l.id(), 'name': l.name(), 'type': t})
            result.sort(key=lambda x: x['name'].lower())
            return result
        except Exception as e:
            print(f"GeoMetadata [list_layers]: {e}")
            return []

    @pyqtSlot(str)
    def set_active_layer(self, layer_id: str):
        """Define a camada ativa no painel de camadas do QGIS."""
        try:
            from qgis.core import QgsProject
            plugin = getattr(self._dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
            layer  = QgsProject.instance().mapLayer(layer_id)
            if layer and iface:
                iface.setActiveLayer(layer)
        except Exception as e:
            print(f"GeoMetadata [set_active_layer]: {e}")

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
            "is_logged": is_logged,
            "cda_url": config_loader.get_cda_url()
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

    @pyqtSlot(str)
    def open_file_location(self, file_path: str):
        """Abre o Explorer na pasta do arquivo, com o arquivo já selecionado/destacado."""
        import os
        import subprocess
        try:
            norm_path = os.path.normpath(file_path)
            if os.name == 'nt':
                # Forma de string (não lista) é a que funciona de forma confiável com
                # caminhos com espaço — o explorer.exe faz seu próprio parsing da linha
                # de comando, então as aspas em volta do caminho precisam chegar literais.
                subprocess.Popen(f'explorer /select,"{norm_path}"')
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(norm_path)])
        except Exception as e:
            print(f"GeoMetadata [open_file_location]: {e}")

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

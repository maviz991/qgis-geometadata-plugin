# -*- coding: utf-8 -*-
"""
main_bridge.py - GeoMetadata Plugin
=====================================
Ponte de comunicação genérica (app-shell) para a interface principal em HTML:
navegação, camadas do QGIS, login/logout, e utilidades sem domínio específico
(toast, abrir pasta no explorer). Exposto ao JS via QWebChannel como 'bridge'.

Lógica específica de GeoNetwork está em geonetwork_bridge.py ('gnBridge') e de
GeoServer em geoserver_bridge.py ('gsBridge').
"""

import os
from qgis.PyQt.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
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
    service_status_ready = pyqtSignal(str, str)  # service ('geonetwork'|'geoserver'), status ('active'|'unstable'|'offline') - ver check_services_status

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._form_manager = getattr(dialog, 'form_manager', None)
        self._sso_widget = None
        self._adm_worker = None
        self._status_workers = []  # ver check_services_status/_on_service_status_done
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
        """Inicia autenticação SSO corporativa via sessão do gateway georchestra.

        O gateway só aceita login via navegador (OAuth2 Client + sessão/cookie) -
        não valida Bearer JWT obtido direto do Azure AD. Por isso trocamos o
        conteúdo da janela (content_stack) por uma QWebEngineView embutida
        apontando pro /oauth2/authorization/entraid do próprio gateway, deixamos
        o redirect completo rodar e capturamos o cookie de sessão resultante
        (ver GatewaySSOWidget) - sem abrir nenhuma janela separada."""
        try:
            from ..core.plugin_config import config_loader
            from .gateway_login_dialog import GatewaySSOWidget
            base_url = config_loader.get_gateway_base_url()
            if not base_url:
                self.login_error.emit("URL do GeoServer não está definida no config.json.")
                return
            verify_url = f"{config_loader.get_geonetwork_base_url().rstrip('/')}/srv/api/me"

            self.login_loading.emit("Aguardando login no navegador...")
            stack = self._dialog.content_stack
            self._sso_widget = GatewaySSOWidget(base_url, verify_url, parent=stack)
            self._sso_widget.login_succeeded.connect(self._on_gateway_login_succeeded)
            self._sso_widget.login_failed.connect(self._on_gateway_login_failed)
            stack.addWidget(self._sso_widget)
            stack.setCurrentWidget(self._sso_widget)
        except Exception as e:
            self.login_error.emit(str(e))

    def _leave_sso_widget(self):
        stack = self._dialog.content_stack
        stack.setCurrentWidget(self._dialog.web_view)
        if self._sso_widget is not None:
            stack.removeWidget(self._sso_widget)
            self._sso_widget.deleteLater()
            self._sso_widget = None

    def _on_gateway_login_succeeded(self, session, username):
        self._leave_sso_widget()
        self._dialog.plugin.api_session = session
        self._dialog.plugin.auth_username = username
        self._dialog.update_ui_for_login_status()

    def _on_gateway_login_failed(self, msg):
        self._leave_sso_widget()
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
        # Limpa também credenciais REST do GeoServer ao sair
        self._dialog.plugin.gs_rest_session = None
        self._dialog.plugin.gs_rest_username = None
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
            "cda_url": config_loader.get_cda_url(),
            "docs_url": self._resolve_docs_url()
        }

    def _resolve_docs_url(self):
        """URL do manual (card "Documentação" da Home). Se 'docs_url' estiver
        configurado em config.json (depois de publicado no MinIO), usa ele. Até lá,
        abre o manual local em docs_site/dist/index.html direto do disco - o clique
        passa por window.open() no JS, que o _ExternalLinkPage.createWindow()
        (GeoMetadata_dialog.py) redireciona pro navegador padrão do sistema mesmo
        sendo um file://, então não precisa de servidor nenhum pra funcionar."""
        configured = config_loader.get_docs_url()
        if configured:
            return configured
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local_index = os.path.join(plugin_root, 'docs_site', 'dist', 'index.html')
        if os.path.isfile(local_index):
            return QUrl.fromLocalFile(local_index).toString()
        return ""

    @pyqtSlot()
    def check_services_status(self):
        """Dispara um ping (sem exigir login - deslogado é o caso de uso normal aqui) no
        GeoNetwork e no GeoServer, pra alimentar o badge de status dos cards da Home
        ("Ativo"/"Instável"/"Offline" - antes era um texto "Ativo" fixo no HTML, sem
        relação nenhuma com a realidade). Fire-and-forget (RNF02) - cada checagem roda no
        próprio _ServiceStatusWorker e emite service_status_ready quando terminar; os dois
        serviços são independentes (um pode estar de pé com o outro fora).

        Aponta pro destino REAL de cada serviço pra um visitante DESLOGADO (confirmado
        testando manualmente no navegador) - a URL base crua não é confiável: geonetwork
        depende de um fragmento de rota client-side (.../catalog.search#/home) que o
        navegador só aplica via JS depois de carregar (nunca chega no `requests` - fragmento
        não vai pro servidor). geoserver é ainda mais específico: logado, .../geoserver
        redireciona pro console web de verdade (.../web/, com um "?N" de cache-busting só
        de JS); deslogado, o gateway/proxy de segurança redireciona pra uma página de
        entrada diferente (.../index.html) - usar .../web/ aqui daria sempre "Offline"/
        "Instável" pra quem não está logado, exatamente o caso de uso mais comum desse
        badge. Usar a URL exata que o servidor entrega pro caso deslogado evita depender de
        `requests` reproduzir um redirect condicionado à sessão."""
        from .status_workers import _ServiceStatusWorker
        targets = {
            'geonetwork': config_loader.get_geonetwork_base_url().rstrip('/') + '/srv/por/catalog.search',
            'geoserver': config_loader.get_geoserver_url().rstrip('/') + '/index.html',
        }
        for service, url in targets.items():
            worker = _ServiceStatusWorker(service, url)
            self._status_workers.append(worker)
            worker.done.connect(self._on_service_status_done)
            worker.start()

    def _on_service_status_done(self, service, status):
        worker = self.sender()
        if worker in self._status_workers:
            self._status_workers.remove(worker)
        self.service_status_ready.emit(service, status)

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
                # caminhos com espaço - o explorer.exe faz seu próprio parsing da linha
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

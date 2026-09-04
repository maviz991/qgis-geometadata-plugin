# -*- coding: utf-8 -*-
"""
login_dialog.py - GeoMetadata Plugin
=====================================
Diálogo de autenticação unificado.

  Modo HTML  (QWebEngineView disponível): UI renderizada em login.html
  Modo QSS   (fallback):                  UI em widgets PyQt5 puros

A mesma API pública funciona em ambos os modos:
    dialog.exec_()
    dialog.get_session()   -> requests.Session
    dialog.get_username()  -> str
"""

import os
import base64
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QSizePolicy
)
from qgis.PyQt.QtCore import Qt, QUrl, QThread, pyqtSignal
from qgis.PyQt.QtGui import QPixmap, QIcon

from ..core.entra_auth_provider import EntraAuthProvider

_PLUGIN_ROOT   = os.path.dirname(os.path.dirname(__file__))
_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "login.html")
_LOGO_PATH     = os.path.join(_PLUGIN_ROOT, "img", "logo.png")
_FAVICON_PATH  = os.path.join(_PLUGIN_ROOT, "img", "favcon_cdhu.png")
_ACCENT        = "#e5222d"
_ACCENT_HOVER  = "#c0111b"


def _b64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Workers compartilhados (ambos os modos usam)
# ---------------------------------------------------------------------------
class _SsoWorker(QThread):
    auth_success = pyqtSignal(object)
    auth_failed  = pyqtSignal(str)

    def __init__(self, provider: EntraAuthProvider):
        super().__init__()
        self._provider = provider

    def run(self):
        try:
            if self._provider.authenticate_interactive():
                self.auth_success.emit(self._provider)
            else:
                self.auth_failed.emit(self._provider.get_error() or "Autenticação cancelada.")
        except Exception as e:
            self.auth_failed.emit(str(e))


class _AdminWorker(QThread):
    login_success = pyqtSignal(object, str)
    login_failed  = pyqtSignal(str)

    def __init__(self, user: str, password: str, geoserver_url: str):
        super().__init__()
        self._user     = user
        self._password = password
        self._url      = f"{geoserver_url.rstrip('/')}/ows?version=1.3.0"

    def run(self):
        try:
            session        = requests.Session()
            session.verify = False
            session.auth   = (self._user, self._password)
            resp = session.get(self._url, timeout=12)
            if resp.status_code == 401:
                self.login_failed.emit("Usuário ou senha inválidos.")
            elif resp.status_code == 403:
                self.login_failed.emit("Acesso negado. Verifique as permissões do usuário.")
            else:
                self.login_success.emit(session, self._user)
        except requests.exceptions.ConnectionError:
            self.login_failed.emit("Sem conexão com o servidor. Verifique a rede ou VPN.")
        except requests.exceptions.Timeout:
            self.login_failed.emit("Servidor não respondeu. Tente novamente.")
        except Exception as e:
            self.login_failed.emit(str(e))


# ---------------------------------------------------------------------------
# LoginDialog - roteador HTML vs QSS
# ---------------------------------------------------------------------------
class LoginDialog(QDialog):
    """
    Diálogo de login unificado.
    Usa QWebEngineView + HTML se disponível, cai para QSS widgets caso contrário.
    """

    def __init__(self, client_id: str, tenant_id: str, scopes: list,
                 geoserver_url: str, parent=None):
        super().__init__(parent)
        self._client_id     = client_id
        self._tenant_id     = tenant_id
        self._scopes        = scopes
        self._geoserver_url = geoserver_url
        self._session       = None
        self._username      = ""
        self._sso_worker    = None
        self._adm_worker    = None
        self._installer     = None
        self._bridge        = None

        self.setWindowTitle("Geohab | Identificação")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        icon_pix = QPixmap(_FAVICON_PATH)
        if not icon_pix.isNull():
            self.setWindowIcon(QIcon(icon_pix))

        # Tenta importar o WebEngine de forma robusta
        try:
            # 1. Tenta via wrapper do QGIS
            try:
                from qgis.PyQt.QtWebEngineWidgets import QWebEngineView
                from qgis.PyQt.QtWebChannel import QWebChannel
            except ImportError:
                # 2. Se falhar (comum em instalações pip), tenta direto no PyQt5
                from PyQt5.QtWebEngineWidgets import QWebEngineView
                from PyQt5.QtWebChannel import QWebChannel
            
            self._init_web(QWebEngineView, QWebChannel)
            
        except (ImportError, RuntimeError) as e:
            # Se falhar, avisamos o usuário que o ambiente está quebrado.
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(
                self, "Erro de Dependência",
                f"PyQtWebEngine não pôde ser carregado.\n\n"
                f"O plugin exige esta biblioteca para o login corporativo.\n"
                f"Erro: {str(e)}"
            )
            self.reject()

    # ==================================================================
    # MODO HTML (Único modo ativo conforme solicitação)
    # ==================================================================

    def _init_web(self, QWebEngineView, QWebChannel):
        from .web_bridge import LoginBridge

        self.setFixedSize(480, 600)

        self._bridge = LoginBridge(
            client_id=self._client_id,
            tenant_id=self._tenant_id,
            scopes=self._scopes,
            geoserver_url=self._geoserver_url,
            dialog=self,
            parent=self,
        )

        view = QWebEngineView(self)
        view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        channel = QWebChannel(view.page())
        channel.registerObject("bridge", self._bridge)
        view.page().setWebChannel(channel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        try:
            with open(_TEMPLATE_PATH, encoding="utf-8") as f:
                html = f.read()
            html = html.replace("{LOGO_B64}",    _b64(_LOGO_PATH))
            html = html.replace("{FAVICON_B64}", _b64(_FAVICON_PATH))
        except OSError:
            html = "<h3 style='color:red;padding:20px'>Template login.html não encontrado.</h3>"

        view.page().setHtml(html, QUrl("qrc:///"))

    # ==================================================================
    # API pública
    # ==================================================================

    def get_session(self):
        if self._bridge is not None:
            return self._bridge.session
        return None

    def get_username(self) -> str:
        if self._bridge is not None:
            return self._bridge.username
        return ""

    def closeEvent(self, event):
        """Para as QThreads do LoginBridge antes de destruir o diálogo.

        start_sso() bloqueia em EntraAuthProvider.authenticate_interactive() (login via
        navegador - pode levar minutos) rodando em _sso_worker; start_admin() e
        run_install() têm o mesmo padrão em _adm_worker/_installer. Fechar este modal (X,
        Esc, ou clique duplo em "Cancelar") enquanto qualquer um desses ainda está em
        execução destrói a QThread ainda rodando - Qt chama std::terminate(), que fecha o
        QGIS inteiro silenciosamente, sem crash dump (mesma causa raiz documentada em
        GeoMetadataDialog.closeEvent, GeoMetadata_dialog.py)."""
        bridge = getattr(self, '_bridge', None)
        if bridge:
            for attr in ('_sso_worker', '_adm_worker', '_installer'):
                w = getattr(bridge, attr, None)
                if w and w.isRunning():
                    w.quit()
                    # 10s (não 2s) - mesmo raciocínio de GeoMetadataDialog.closeEvent: quit()
                    # não interrompe de verdade um run() síncrono bloqueante (request/pip),
                    # só wait() dá tempo real da chamada terminar sozinha.
                    w.wait(10000)
        super().closeEvent(event)


# ==================================================================
# WORKERS (Processamento em Background)
# ==================================================================

class _SsoWorker(QThread):
    """Worker para não travar a UI durante o login no navegador."""
    auth_success = pyqtSignal(object)  # passa o provider
    auth_failed  = pyqtSignal(str)

    def __init__(self, provider: EntraAuthProvider):
        super().__init__()
        self.provider = provider

    def run(self):
        try:
            self.provider.authenticate_interactive()
            if self.provider.get_session():
                self.auth_success.emit(self.provider)
            else:
                self.auth_failed.emit("Falha ao obter sessão.")
        except Exception as e:
            self.auth_failed.emit(str(e))


class _AdminWorker(QThread):
    """Worker para autenticação via formulário local (GeoServer)."""
    login_success = pyqtSignal(object, str)  # session, username
    login_failed  = pyqtSignal(str)

    def __init__(self, user, pw, geoserver_url):
        super().__init__()
        self.user = user
        self.pw   = pw
        self.url  = geoserver_url

    def run(self):
        try:
            # Tenta autenticar no GeoServer (Basic Auth)
            s = requests.Session()
            s.auth = (self.user, self.pw)
            # Testa a conexão
            test_url = f"{self.url.rstrip('/')}/rest/layers.json"
            r = s.get(test_url, timeout=10, verify=False)
            
            if r.status_code == 200:
                self.login_success.emit(s, self.user)
            elif r.status_code == 401:
                self.login_failed.emit("Usuário ou senha incorretos.")
            else:
                self.login_failed.emit(f"Erro no servidor: {r.status_code}")
        except Exception as e:
            self.login_failed.emit(f"Falha de rede: {str(e)}")

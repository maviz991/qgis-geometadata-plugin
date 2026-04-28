# -*- coding: utf-8 -*-
"""
login_dialog.py — GeoMetadata Plugin
=====================================
Diálogo de autenticação unificado.

  1. Conta Corporativa — Microsoft Entra ID (SSO / PKCE)
  2. Administrador     — usuário + senha locais (Basic Auth)

Autor: GeoMetadata Plugin | CDHU
"""

import os
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QWidget, QLineEdit, QFrame
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QSize
from qgis.PyQt.QtGui import QPixmap, QIcon

from ..core.entra_auth_provider import EntraAuthProvider, is_msal_available
from ..core.dependency_installer import DependencyInstaller

_PLUGIN_ROOT  = os.path.dirname(os.path.dirname(__file__))
_LOGO_PATH    = os.path.join(_PLUGIN_ROOT, "img", "logo.png")
_FAVICON_PATH = os.path.join(_PLUGIN_ROOT, "img", "favcon_cdhu.png")
_ACCENT       = "#e5222d"
_ACCENT_HOVER = "#c0111b"


# ---------------------------------------------------------------------------
# Worker — SSO (Entra ID) em background
# ---------------------------------------------------------------------------
class _SsoWorker(QThread):
    auth_success = pyqtSignal(object)  # EntraAuthProvider
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


# ---------------------------------------------------------------------------
# Worker — Basic Auth em background
# ---------------------------------------------------------------------------
class _AdminWorker(QThread):
    login_success = pyqtSignal(object, str)  # session, username
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
                # 200 ou qualquer outra resposta = servidor alcançado, credenciais aceitas
                self.login_success.emit(session, self._user)
        except requests.exceptions.ConnectionError:
            self.login_failed.emit("Sem conexão com o servidor. Verifique a rede ou VPN.")
        except requests.exceptions.Timeout:
            self.login_failed.emit("Servidor não respondeu. Tente novamente.")
        except Exception as e:
            self.login_failed.emit(str(e))


# ---------------------------------------------------------------------------
# LoginDialog
# ---------------------------------------------------------------------------
class LoginDialog(QDialog):
    """
    Diálogo de autenticação unificado (SSO + Admin local).

    Após exec_() retornar Accepted:
        session  = dialog.get_session()   # requests.Session autenticada
        username = dialog.get_username()  # nome / e-mail do usuário
    """

    def __init__(self, client_id: str, tenant_id: str, scopes: list,
                 geoserver_url: str, parent=None):
        super().__init__(parent)
        self._client_id    = client_id
        self._tenant_id    = tenant_id
        self._scopes       = scopes
        self._geoserver_url = geoserver_url
        self._session      = None
        self._username     = ""
        self._sso_worker   = None
        self._adm_worker   = None
        self._installer    = None

        self._build_ui()
        self.setWindowTitle("Geohab | Identificação")
        self.setFixedWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(self._stylesheet())

        if not is_msal_available():
            self._enter_install_mode()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 24)
        root.setSpacing(0)

        # Logo
        root.addWidget(self._make_logo(), 0, Qt.AlignHCenter)
        root.addSpacing(6)

        tagline = QLabel("Autentique-se para acessar o Geohab")
        tagline.setObjectName("Tagline")
        tagline.setAlignment(Qt.AlignCenter)
        root.addWidget(tagline)
        root.addSpacing(28)

        # Card Corporativo
        root.addWidget(self._build_sso_card())
        root.addSpacing(16)

        # Divisor
        root.addWidget(self._make_divider())
        root.addSpacing(16)

        # Card Administrador
        root.addWidget(self._build_admin_card())
        root.addSpacing(20)

        # Cancelar
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("CancelBtn")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_cancel)
        row.addStretch()
        root.addLayout(row)

    def _make_logo(self) -> QLabel:
        lbl = QLabel()
        pix = QPixmap(_LOGO_PATH)
        if not pix.isNull():
            lbl.setPixmap(pix.scaledToHeight(64, Qt.SmoothTransformation))
        else:
            lbl.setText("<b style='font-size:24px;color:#e5222d;'>GEOHAB</b>")
            lbl.setTextFormat(Qt.RichText)
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _make_divider(self) -> QWidget:
        w   = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        for side in ("L", "R"):
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setObjectName("DivLine")
            if side == "L":
                row.addWidget(line, 1)
                lbl = QLabel("acesso administrativo")
                lbl.setObjectName("DivText")
                row.addWidget(lbl)
            else:
                row.addWidget(line, 1)
        return w

    # ------ Card SSO -------------------------------------------------------

    def _build_sso_card(self) -> QFrame:
        self._sso_card = QFrame()
        self._sso_card.setObjectName("SsoCard")
        lyt = QVBoxLayout(self._sso_card)
        lyt.setContentsMargins(20, 18, 20, 18)
        lyt.setSpacing(10)

        # Header do card
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(self._lbl("Conta Corporativa", bold=True))
        col.addWidget(self._lbl("Entre com sua conta CDHU",
                                size=11, color="#64748b"))
        hdr.addLayout(col)
        hdr.addStretch()
        lyt.addLayout(hdr)

        # Status + progress
        self._sso_status = QLabel("")
        self._sso_status.setObjectName("Status")
        self._sso_status.setAlignment(Qt.AlignCenter)
        self._sso_status.setWordWrap(True)
        self._sso_status.setTextFormat(Qt.RichText)
        self._sso_status.setVisible(False)
        lyt.addWidget(self._sso_status)

        self._sso_prog = QProgressBar()
        self._sso_prog.setRange(0, 0)
        self._sso_prog.setFixedHeight(4)
        self._sso_prog.setVisible(False)
        lyt.addWidget(self._sso_prog)

        # Botão SSO
        self._btn_sso = QPushButton()
        self._btn_sso.setObjectName("SsoBtn")
        self._btn_sso.setMinimumHeight(44)
        self._btn_sso.setCursor(Qt.PointingHandCursor)
        pix = QPixmap(_FAVICON_PATH)
        if not pix.isNull():
            self._btn_sso.setIcon(QIcon(pix))
            self._btn_sso.setIconSize(QSize(20, 20))
            self._btn_sso.setText("  Entrar com conta CDHU")
        else:
            self._btn_sso.setText("Entrar com conta CDHU")
        self._btn_sso.clicked.connect(self._start_sso)
        lyt.addWidget(self._btn_sso)

        return self._sso_card

    # ------ Card Admin -----------------------------------------------------

    def _build_admin_card(self) -> QFrame:
        self._admin_card = QFrame()
        self._admin_card.setObjectName("AdminCard")
        lyt = QVBoxLayout(self._admin_card)
        lyt.setContentsMargins(20, 18, 20, 18)
        lyt.setSpacing(10)

        # Header do card
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(self._lbl("Administrador", bold=True))
        col.addWidget(self._lbl("Entre com usuário e senha locais",
                                size=11, color="#64748b"))
        hdr.addLayout(col)
        hdr.addStretch()
        lyt.addLayout(hdr)

        # Campos
        self._f_user = QLineEdit()
        self._f_user.setPlaceholderText("Usuário")
        self._f_user.setObjectName("Field")
        self._f_user.setMinimumHeight(36)
        lyt.addWidget(self._f_user)

        self._f_pass = QLineEdit()
        self._f_pass.setPlaceholderText("Senha")
        self._f_pass.setEchoMode(QLineEdit.Password)
        self._f_pass.setObjectName("Field")
        self._f_pass.setMinimumHeight(36)
        self._f_pass.returnPressed.connect(self._start_admin)
        lyt.addWidget(self._f_pass)

        # Status + progress
        self._adm_status = QLabel("")
        self._adm_status.setObjectName("Status")
        self._adm_status.setWordWrap(True)
        self._adm_status.setTextFormat(Qt.RichText)
        self._adm_status.setVisible(False)
        lyt.addWidget(self._adm_status)

        self._adm_prog = QProgressBar()
        self._adm_prog.setRange(0, 0)
        self._adm_prog.setFixedHeight(4)
        self._adm_prog.setVisible(False)
        lyt.addWidget(self._adm_prog)

        # Botão Admin
        self._btn_admin = QPushButton("Entrar")
        self._btn_admin.setObjectName("AdminBtn")
        self._btn_admin.setMinimumHeight(44)
        self._btn_admin.setCursor(Qt.PointingHandCursor)
        self._btn_admin.clicked.connect(self._start_admin)
        lyt.addWidget(self._btn_admin)

        return self._admin_card

    # ------------------------------------------------------------------
    # Fluxo SSO
    # ------------------------------------------------------------------

    def _enter_install_mode(self):
        self._btn_sso.setObjectName("InstallBtn")
        self._btn_sso.setIcon(QIcon())
        self._btn_sso.setText("⬇  Instalar dependência (msal)")
        self._btn_sso.style().unpolish(self._btn_sso)
        self._btn_sso.style().polish(self._btn_sso)
        self._set_sso_status(
            "<span style='color:#92400e;'>⚠ <b>msal</b> não instalado. "
            "Clique para instalar automaticamente e reinicie o QGIS.</span>"
        )
        self._btn_sso.clicked.disconnect()
        self._btn_sso.clicked.connect(self._run_install)

    def _start_sso(self):
        self._lock(True)
        self._sso_prog.setVisible(True)
        self._set_sso_status("<span style='color:#1a73e8;'>🌐 Aguardando login no navegador...</span>")
        provider = EntraAuthProvider(self._client_id, self._tenant_id, self._scopes)
        self._sso_worker = _SsoWorker(provider)
        self._sso_worker.auth_success.connect(self._on_sso_ok)
        self._sso_worker.auth_failed.connect(self._on_sso_fail)
        self._sso_worker.start()

    def _on_sso_ok(self, provider: EntraAuthProvider):
        self._session  = provider.get_session()
        self._username = provider.get_username()
        self.accept()

    def _on_sso_fail(self, msg: str):
        self._sso_prog.setVisible(False)
        self._set_sso_status(f"<span style='color:#d93025;'>❌ {msg}</span>")
        self._lock(False)

    # ------------------------------------------------------------------
    # Fluxo instalação msal
    # ------------------------------------------------------------------

    def _run_install(self):
        self._lock(True)
        self._sso_prog.setVisible(True)
        self._set_sso_status("<span style='color:#1a73e8;'>Instalando msal, aguarde...</span>")
        self._installer = DependencyInstaller("msal")
        self._installer.install_success.connect(self._on_install_ok)
        self._installer.install_failed.connect(self._on_install_fail)
        self._installer.start()

    def _on_install_ok(self, _pkg: str):
        self._sso_prog.setVisible(False)
        self._set_sso_status(
            "<span style='color:#2e7d32;'>✅ msal instalado! "
            "<b>Reinicie o QGIS</b> e clique em Entrar.</span>"
        )
        self._btn_sso.setEnabled(False)
        self._f_user.setEnabled(True)
        self._f_pass.setEnabled(True)
        self._btn_admin.setEnabled(True)

    def _on_install_fail(self, _pkg: str, _err: str):
        self._sso_prog.setVisible(False)
        self._set_sso_status(
            "<span style='color:#d93025;'>❌ Falha. Abra o <b>OSGeo4W Shell</b> "
            "e execute: <code>pip install msal</code></span>"
        )
        self._lock(False)

    # ------------------------------------------------------------------
    # Fluxo Admin
    # ------------------------------------------------------------------

    def _start_admin(self):
        user = self._f_user.text().strip()
        pw   = self._f_pass.text()
        if not user or not pw:
            self._set_adm_status("<span style='color:#d93025;'>❌ Preencha usuário e senha.</span>")
            return
        self._lock(True)
        self._adm_prog.setVisible(True)
        self._set_adm_status("<span style='color:#1a73e8;'>Verificando credenciais...</span>")
        self._adm_worker = _AdminWorker(user, pw, self._geoserver_url)
        self._adm_worker.login_success.connect(self._on_admin_ok)
        self._adm_worker.login_failed.connect(self._on_admin_fail)
        self._adm_worker.start()

    def _on_admin_ok(self, session, username: str):
        self._session  = session
        self._username = username
        self.accept()

    def _on_admin_fail(self, msg: str):
        self._adm_prog.setVisible(False)
        self._set_adm_status(f"<span style='color:#d93025;'>❌ {msg}</span>")
        self._lock(False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _lock(self, locked: bool):
        self._btn_sso.setEnabled(not locked)
        self._btn_admin.setEnabled(not locked)
        self._f_user.setEnabled(not locked)
        self._f_pass.setEnabled(not locked)
        if not locked:
            self._sso_prog.setVisible(False)
            self._adm_prog.setVisible(False)

    def _set_sso_status(self, html: str):
        self._sso_status.setText(html)
        self._sso_status.setVisible(bool(html))

    def _set_adm_status(self, html: str):
        self._adm_status.setText(html)
        self._adm_status.setVisible(bool(html))

    @staticmethod
    def _lbl(text: str, bold=False, size=13, color="#1e293b") -> QLabel:
        lbl = QLabel(text)
        s = f"font-size:{size}px; color:{color};"
        if bold:
            s += " font-weight:700;"
        lbl.setStyleSheet(s)
        return lbl

    def get_session(self):
        return self._session

    def get_username(self) -> str:
        return self._username

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    def _stylesheet(self) -> str:
        return f"""
        QDialog {{
            background-color: #ffffff;
        }}

        #Tagline {{
            font-size: 12px;
            color: #64748b;
        }}

        /* Cards */
        #SsoCard {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
        }}
        #AdminCard {{
            background: #fff8f8;
            border: 1px solid #fecaca;
            border-radius: 12px;
        }}

        /* Divisor */
        #DivLine {{ color: #e2e8f0; }}
        #DivText {{
            color: #94a3b8;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
        }}

        /* Campos de texto */
        #Field {{
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 0 10px;
            font-size: 13px;
            background: #ffffff;
        }}
        #Field:focus {{
            border: 2px solid {_ACCENT};
            background: #ffffff;
        }}

        /* Botão SSO */
        #SsoBtn {{
            background-color: #1e293b;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-weight: 700;
            font-size: 13px;
        }}
        #SsoBtn:hover  {{ background-color: #334155; }}
        #SsoBtn:disabled {{ background-color: #94a3b8; }}

        /* Botão instalar msal */
        #InstallBtn {{
            background-color: #b45309;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-weight: 700;
            font-size: 13px;
        }}
        #InstallBtn:hover {{ background-color: #92400e; }}
        #InstallBtn:disabled {{ background-color: #d97706; }}

        /* Botão Admin */
        #AdminBtn {{
            background-color: {_ACCENT};
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-weight: 700;
            font-size: 13px;
        }}
        #AdminBtn:hover    {{ background-color: {_ACCENT_HOVER}; }}
        #AdminBtn:disabled {{ background-color: #fca5a5; }}

        /* Cancelar */
        #CancelBtn {{
            background: transparent;
            border: none;
            color: #64748b;
            font-size: 12px;
            font-weight: 600;
            padding: 6px 16px;
        }}
        #CancelBtn:hover {{ color: {_ACCENT}; text-decoration: underline; }}

        /* Status e progresso */
        #Status {{ font-size: 12px; }}

        QProgressBar {{
            background-color: #f1f5f9;
            border: none;
            border-radius: 2px;
        }}
        QProgressBar::chunk {{
            background-color: {_ACCENT};
            border-radius: 2px;
        }}
        """

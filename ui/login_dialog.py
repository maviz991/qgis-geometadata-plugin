# -*- coding: utf-8 -*-
"""
login_dialog.py — GeoMetadata Plugin
===========================================
Diálogo de login unificado: SSO (Entra ID) + Administrador (Local).

Este componente substitui o fluxo anterior que roteava para diálogos separados.
Se msal não estiver instalado, oferece a instalação inline no card Corporativo.

Autor: GeoMetadata Plugin | CDHU
"""

import os
import requests
import urllib3
import re
from typing import Optional

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QWidget, QLineEdit, QFrame
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from qgis.PyQt.QtGui import QIcon, QPixmap, QFont

from ..core.entra_auth_provider import EntraAuthProvider, is_msal_available
from ..core.dependency_installer import DependencyInstaller
from ..core.plugin_config import config_loader

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Workers — roda a autenticação em threads separadas
# ---------------------------------------------------------------------------

class _AuthWorker(QThread):
    """Executa o fluxo interativo do MSAL em background."""
    auth_success = pyqtSignal(object)  # EntraAuthProvider
    auth_failed  = pyqtSignal(str)     # mensagem de erro

    def __init__(self, provider: EntraAuthProvider):
        super().__init__()
        self._provider = provider

    def run(self):
        try:
            success = self._provider.authenticate_interactive()
            if success:
                self.auth_success.emit(self._provider)
            else:
                error = self._provider.get_error()
                self.auth_failed.emit(error or "Autenticação cancelada ou falhou.")
        except Exception as e:
            self.auth_failed.emit(str(e))


class _AdminWorker(QThread):
    """Verifica credenciais Basic Auth contra o GeoServer."""
    success = pyqtSignal(object, str)  # (requests.Session, username)
    failed  = pyqtSignal(str)          # mensagem de erro

    def __init__(self, url: str, user: str, password: str):
        super().__init__()
        self._url = url
        self._user = user
        self._password = password

    def run(self):
        session = requests.Session()
        session.verify = False
        session.auth = (self._user, self._password)
        
        # Testamos contra o GetCapabilities do WMS ou apenas a URL base + ows
        test_url = f"{self._url.rstrip('/')}/ows?version=1.3.0"
        
        try:
            response = session.get(test_url, timeout=12, verify=False)
            if response.status_code == 401:
                self.failed.emit("Usuário ou senha inválidos.")
            elif response.status_code >= 400:
                self.failed.emit(f"Servidor retornou erro {response.status_code}.")
            else:
                self.success.emit(session, self._user)
        except requests.exceptions.RequestException as e:
            self.failed.emit(f"Falha de conexão: {str(e)}")
        except Exception as e:
            self.failed.emit(str(e))


# ---------------------------------------------------------------------------
# LoginDialog — Janela Unificada
# ---------------------------------------------------------------------------

class LoginDialog(QDialog):
    """
    Diálogo de login consolidado.
    
    Retorna Accepted se autenticado com sucesso.
    """

    ACCENT_COLOR = "#e5222d"
    ACCENT_HOVER = "#c0111b"

    def __init__(self, client_id: str, tenant_id: str, scopes: list, geoserver_url: str, parent=None):
        super().__init__(parent)
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._scopes = scopes
        self._geoserver_url = geoserver_url

        self._session: Optional[requests.Session] = None
        self._username: Optional[str] = None
        self._worker = None
        self._installer = None

        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Geohab | Identificação")
        self.setFixedSize(480, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(self._get_base_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(35, 30, 35, 20)
        main_layout.setSpacing(0)

        # 1. Logo
        logo_container = QHBoxLayout()
        logo_container.addStretch()
        self._logo_label = QLabel()
        self._load_logo()
        logo_container.addWidget(self._logo_label)
        logo_container.addStretch()
        main_layout.addLayout(logo_container)
        main_layout.addSpacing(30)

        # 2. Seção Corporativa (Entra ID)
        self._card_sso = self._build_sso_card()
        main_layout.addWidget(self._card_sso)
        main_layout.addSpacing(20)

        # 3. Divisor
        main_layout.addLayout(self._build_divider("ou"))
        main_layout.addSpacing(20)

        # 4. Seção Administrador (Basic Auth)
        self._card_admin = self._build_admin_card()
        main_layout.addWidget(self._card_admin)
        main_layout.addStretch()

        # 5. Botão Cancelar
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setObjectName("CancelButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        
        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        cancel_layout.addWidget(cancel_btn)
        cancel_layout.addStretch()
        main_layout.addLayout(cancel_layout)

        # Estado inicial (msal check)
        if not is_msal_available():
            self._set_sso_install_mode()

    def _load_logo(self):
        """Carrega o logo diretamente do sistema de arquivos."""
        try:
            # Sobe 1 nível (ui -> root) depois img/logo.png
            plugin_root = os.path.dirname(os.path.dirname(__file__))
            logo_path = os.path.join(plugin_root, 'img', 'logo.png')
            
            if os.path.exists(logo_path):
                pix = QPixmap(logo_path)
                scaled = pix.scaledToHeight(55, Qt.SmoothTransformation)
                self._logo_label.setPixmap(scaled)
            else:
                # Fallback se o arquivo sumir
                self._logo_label.setText("<b style='font-size:24px; color:#e5222d;'>GEOHAB</b>")
        except Exception:
            pass

    def _build_sso_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(12)

        title = QLabel("Corporativo")
        title.setObjectName("SectionTitle")
        lyt.addWidget(title)

        plugin_root = os.path.dirname(os.path.dirname(__file__))
        icon_path = os.path.join(plugin_root, 'img', 'favcon_cdhu.png')
        
        self._btn_sso = QPushButton(" Entrar com conta CDHU")
        if os.path.exists(icon_path):
            self._btn_sso.setIcon(QIcon(icon_path))
            self._btn_sso.setIconSize(QSize(18, 18))
            
        self._btn_sso.setObjectName("SSOButton")
        self._btn_sso.setCursor(Qt.PointingHandCursor)
        self._btn_sso.setFixedHeight(45)
        self._btn_sso.clicked.connect(self._start_sso_auth)
        lyt.addWidget(self._btn_sso)

        self._sso_status = QLabel("")
        self._sso_status.setObjectName("StatusLabel")
        self._sso_status.setWordWrap(True)
        self._sso_status.setAlignment(Qt.AlignCenter)
        lyt.addWidget(self._sso_status)

        self._sso_progress = QProgressBar()
        self._sso_progress.setRange(0, 0)
        self._sso_progress.setVisible(False)
        self._sso_progress.setFixedHeight(4)
        lyt.addWidget(self._sso_progress)

        return card

    def _build_admin_card(self) -> QFrame:
        card = QFrame()
        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(10)

        title = QLabel("Administrador")
        title.setObjectName("SectionTitle")
        lyt.addWidget(title)

        self._le_user = QLineEdit()
        self._le_user.setPlaceholderText("Usuário")
        self._le_user.setFixedHeight(38)
        lyt.addWidget(self._le_user)

        self._le_pass = QLineEdit()
        self._le_pass.setPlaceholderText("Senha")
        self._le_pass.setEchoMode(QLineEdit.Password)
        self._le_pass.setFixedHeight(38)
        self._le_pass.returnPressed.connect(self._start_admin_auth)
        lyt.addWidget(self._le_pass)

        self._btn_admin = QPushButton("Entrar")
        self._btn_admin.setObjectName("AdminButton")
        self._btn_admin.setCursor(Qt.PointingHandCursor)
        self._btn_admin.setFixedHeight(40)
        self._btn_admin.clicked.connect(self._start_admin_auth)
        lyt.addWidget(self._btn_admin)

        self._admin_status = QLabel("")
        self._admin_status.setObjectName("StatusLabel")
        self._admin_status.setWordWrap(True)
        self._admin_status.setAlignment(Qt.AlignCenter)
        lyt.addWidget(self._admin_status)

        self._admin_progress = QProgressBar()
        self._admin_progress.setRange(0, 0)
        self._admin_progress.setVisible(False)
        self._admin_progress.setFixedHeight(4)
        lyt.addWidget(self._admin_progress)

        return card

    def _build_divider(self, text: str) -> QHBoxLayout:
        lyt = QHBoxLayout()
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setObjectName("DividerLine")
        
        lbl = QLabel(text)
        lbl.setObjectName("DividerText")
        
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setObjectName("DividerLine")
        
        lyt.addWidget(line1)
        lyt.addWidget(lbl)
        lyt.addWidget(line2)
        return lyt

    # ------------------------------------------------------------------
    # Lógica SSO (Entra ID)
    # ------------------------------------------------------------------

    def _set_sso_install_mode(self):
        self._btn_sso.setText("⬇  Instalar msal (necessário)")
        self._btn_sso.setStyleSheet(f"background-color: #334155;")
        self._sso_status.setText(
            "<span style='color:#64748b; font-size:11px;'>"
            "A biblioteca corporal é necessária para este método."
            "</span>"
        )
        try:
            self._btn_sso.clicked.disconnect()
        except: pass
        self._btn_sso.clicked.connect(self._run_install)

    def _run_install(self):
        self._btn_sso.setEnabled(False)
        self._sso_progress.setVisible(True)
        self._sso_status.setText("<span style='color:#1a73e8;'>Instalando, aguarde...</span>")
        
        self._installer = DependencyInstaller("msal")
        self._installer.install_success.connect(self._on_install_ok)
        self._installer.install_failed.connect(self._on_install_err)
        self._installer.start()

    def _on_install_ok(self):
        self._sso_progress.setVisible(False)
        self._sso_status.setText(
            "<span style='color:#10b981;'><b>✅ Pronto!</b> Reinicie o QGIS para ativar.</span>"
        )

    def _on_install_err(self, pkg, err):
        self._sso_progress.setVisible(False)
        self._sso_status.setText(f"<span style='color:#d93025;'>Falha: {err[:50]}...</span>")
        self._btn_sso.setEnabled(True)

    def _start_sso_auth(self):
        self._set_busy(True)
        self._sso_status.setText("<span style='color:#1a73e8;'>🌐 Verificando navegador...</span>")
        self._sso_progress.setVisible(True)

        provider = EntraAuthProvider(self._client_id, self._tenant_id, self._scopes)
        self._worker = _AuthWorker(provider)
        self._worker.auth_success.connect(self._on_sso_success)
        self._worker.auth_failed.connect(self._on_sso_failed)
        self._worker.start()

    def _on_sso_success(self, provider: EntraAuthProvider):
        self._session = provider.get_session()
        self._username = provider.get_username()
        self.accept()

    def _on_sso_failed(self, msg):
        self._set_busy(False)
        self._sso_progress.setVisible(False)
        self._sso_status.setText(f"<span style='color:#d93025;'>{msg}</span>")

    # ------------------------------------------------------------------
    # Lógica Admin (Basic)
    # ------------------------------------------------------------------

    def _start_admin_auth(self):
        user = self._le_user.text().strip()
        pwd = self._le_pass.text().strip()
        
        if not user or not pwd:
            self._admin_status.setText("<span style='color:#d93025;'>Preencha todos os campos.</span>")
            return

        self._set_busy(True)
        self._admin_status.setText("<span style='color:#1a73e8;'>Conectando...</span>")
        self._admin_progress.setVisible(True)

        self._worker = _AdminWorker(self._geoserver_url, user, pwd)
        self._worker.success.connect(self._on_admin_success)
        self._worker.failed.connect(self._on_admin_failed)
        self._worker.start()

    def _on_admin_success(self, session, username):
        self._session = session
        self._username = username
        self.accept()

    def _on_admin_failed(self, msg):
        self._set_busy(False)
        self._admin_progress.setVisible(False)
        self._admin_status.setText(f"<span style='color:#d93025;'>{msg}</span>")

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool):
        self._btn_sso.setEnabled(not busy)
        self._btn_admin.setEnabled(not busy)
        self._le_user.setEnabled(not busy)
        self._le_pass.setEnabled(not busy)
        if not busy:
            self._sso_status.setText("")
            self._admin_status.setText("")

    def get_session(self) -> Optional[requests.Session]:
        return self._session

    def get_username(self) -> Optional[str]:
        return self._username

    def _get_base_stylesheet(self) -> str:
        return f"""
            QDialog {{ background-color: #ffffff; }}
            
            #SectionTitle {{
                font-weight: 700;
                font-size: 11px;
                color: #94a3b8;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            
            QLineEdit {{
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 0 12px;
                background-color: #f8fafc;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 2px solid {self.ACCENT_COLOR};
                background-color: #ffffff;
            }}
            
            #SSOButton {{
                background-color: #000000;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-weight: 700;
                font-size: 13px;
            }}
            #SSOButton:hover {{ background-color: #334155; }}
            #SSOButton:disabled {{ background-color: #e2e8f0; color: #94a3b8; }}

            #AdminButton {{
                background-color: {self.ACCENT_COLOR};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-weight: 700;
                font-size: 13px;
            }}
            #AdminButton:hover {{ background-color: {self.ACCENT_HOVER}; }}
            #AdminButton:disabled {{ background-color: #fca5a5; color: #ffffff; }}

            #CancelButton {{
                background: transparent;
                border: none;
                color: #64748b;
                font-weight: 600;
                font-size: 12px;
                padding: 8px 16px;
            }}
            #CancelButton:hover {{ color: {self.ACCENT_COLOR}; text-decoration: underline; }}

            #DividerLine {{ color: #e2e8f0; min-width: 60px; }}
            #DividerText {{ color: #94a3b8; font-size: 12px; font-weight: 600; padding: 0 10px; }}
            
            #StatusLabel {{ font-size: 12px; }}
            
            QProgressBar {{
                background-color: #f1f5f9;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {self.ACCENT_COLOR};
                border-radius: 2px;
            }}
        """

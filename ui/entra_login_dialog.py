# -*- coding: utf-8 -*-
"""
entra_login_dialog.py - GeoMetadata Plugin
===========================================
Diálogo de login via Microsoft Entra ID (OAuth2 + PKCE).

Se msal não estiver instalado, exibe painel de instalação automática
com botão "Instalar Automaticamente" (executa pip em background).

Autor: GeoMetadata Plugin | CDHU
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QWidget
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QSize
from qgis.PyQt.QtGui import QIcon

from ..core.entra_auth_provider import EntraAuthProvider, is_msal_available
from ..core.dependency_installer import DependencyInstaller


# ---------------------------------------------------------------------------
# Worker - roda a autenticação MSAL em thread separada
# ---------------------------------------------------------------------------
class _AuthWorker(QThread):
    """Executa acquire_token_interactive() em background para não travar a UI."""

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
                err = self._provider.get_error() or "Autenticação cancelada ou falhou."
                if 'AADSTS65001' in err or 'AADSTS70011' in err:
                    err = (
                        'Permissão negada pelo Azure AD.\n\n'
                        'O TI precisa configurar a App Registration do GeoOrchestra '
                        'para autorizar o app do plugin como cliente delegado.'
                    )
                self.auth_failed.emit(err)
        except Exception as e:
            self.auth_failed.emit(str(e))


# ---------------------------------------------------------------------------
# EntraLoginDialog - janela de login
# ---------------------------------------------------------------------------
class EntraLoginDialog(QDialog):
    """
    Diálogo de login via Microsoft Entra ID.

    - Se msal estiver instalado: exibe painel de login normal.
    - Se msal estiver ausente: exibe painel de instalação automática.

    Após exec_() bem-sucedido (retorna QDialog.Accepted):
        session  = dialog.get_session()   # requests.Session com Bearer Token
        username = dialog.get_username()  # nome/e-mail do usuário
    """

    def __init__(self, client_id: str, tenant_id: str, scopes: list, parent=None):
        super().__init__(parent)
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._scopes    = scopes
        self._provider  = None
        self._worker    = None
        self._installer = None

        self._build_ui()
        self.setWindowTitle("Entrar com conta CDHU")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Decide qual painel mostrar
        if not is_msal_available():
            self._login_panel.setVisible(False)
            self._install_panel.setVisible(True)

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        # Logo
        title_row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(
            QIcon(":/plugins/geometadata/img/header_logo.png").pixmap(QSize(120, 40))
        )
        title_row.addWidget(logo)
        title_row.addStretch()
        layout.addLayout(title_row)

        layout.addWidget(self._build_login_panel())
        layout.addWidget(self._build_install_panel())

    def _build_login_panel(self) -> QWidget:
        self._login_panel = QWidget()
        lyt = QVBoxLayout(self._login_panel)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(12)

        desc = QLabel(
            "<p style='font-size:13px;'>"
            "Clique em <b>Entrar</b> para autenticar com sua conta corporativa.<br>"
            "O navegador padrão será aberto automaticamente."
            "</p>"
        )
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.RichText)
        lyt.addWidget(desc)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setTextFormat(Qt.RichText)
        lyt.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        lyt.addWidget(self._progress)

        row = QHBoxLayout()
        row.addStretch()
        self._btn_cancel = QPushButton("Cancelar")
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_login = QPushButton("⬛  Entrar com conta CDHU")
        self._btn_login.setDefault(True)
        self._btn_login.setMinimumWidth(200)
        self._btn_login.clicked.connect(self._start_auth)
        row.addWidget(self._btn_cancel)
        row.addWidget(self._btn_login)
        lyt.addLayout(row)

        return self._login_panel

    def _build_install_panel(self) -> QWidget:
        self._install_panel = QWidget()
        lyt = QVBoxLayout(self._install_panel)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(12)

        desc = QLabel(
            "<p style='font-size:13px;'>"
            "A biblioteca <b>msal</b> é necessária para o login com conta corporativa, "
            "mas não está instalada neste ambiente QGIS.</p>"
            "<p>Clique em <b>Instalar Automaticamente</b> e aguarde. "
            "Após a instalação, <b>reinicie o QGIS</b> para continuar.</p>"
        )
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.RichText)
        lyt.addWidget(desc)

        self._install_status = QLabel("")
        self._install_status.setAlignment(Qt.AlignCenter)
        self._install_status.setWordWrap(True)
        self._install_status.setTextFormat(Qt.RichText)
        lyt.addWidget(self._install_status)

        self._install_progress = QProgressBar()
        self._install_progress.setRange(0, 0)
        self._install_progress.setVisible(False)
        self._install_progress.setFixedHeight(6)
        lyt.addWidget(self._install_progress)

        row = QHBoxLayout()
        row.addStretch()
        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.reject)
        self._btn_install = QPushButton("⬇  Instalar Automaticamente")
        self._btn_install.setDefault(True)
        self._btn_install.setMinimumWidth(220)
        self._btn_install.clicked.connect(self._run_install)
        row.addWidget(btn_close)
        row.addWidget(self._btn_install)
        lyt.addLayout(row)

        self._install_panel.setVisible(False)
        return self._install_panel

    # ------------------------------------------------------------------
    # Lógica de autenticação
    # ------------------------------------------------------------------

    def _start_auth(self):
        self._set_login_waiting(True)
        self._status_label.setText(
            "<span style='color:#1a73e8;'>🌐 Aguardando login no navegador...</span>"
        )
        self._provider = EntraAuthProvider(
            client_id=self._client_id,
            tenant_id=self._tenant_id,
            scopes=self._scopes
        )
        self._worker = _AuthWorker(self._provider)
        self._worker.auth_success.connect(self._on_auth_success)
        self._worker.auth_failed.connect(self._on_auth_failed)
        self._worker.start()

    def _on_auth_success(self, provider: EntraAuthProvider):
        self._set_login_waiting(False)
        self._provider = provider
        self.accept()

    def _on_auth_failed(self, error_msg: str):
        self._set_login_waiting(False)
        self._status_label.setText(
            f"<span style='color:#d93025;'>❌ {error_msg}</span>"
        )

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
        self.reject()

    def _set_login_waiting(self, waiting: bool):
        self._btn_login.setEnabled(not waiting)
        self._progress.setVisible(waiting)
        if not waiting:
            self._status_label.setText("")

    # ------------------------------------------------------------------
    # Lógica de instalação do msal
    # ------------------------------------------------------------------

    def _run_install(self):
        self._btn_install.setEnabled(False)
        self._install_progress.setVisible(True)
        self._install_status.setText(
            "<span style='color:#1a73e8;'>Instalando msal, aguarde...</span>"
        )
        self._installer = DependencyInstaller("msal")
        self._installer.install_success.connect(self._on_install_success)
        self._installer.install_failed.connect(self._on_install_failed)
        self._installer.start()

    def _on_install_success(self, _pkg: str):
        self._install_progress.setVisible(False)
        self._install_status.setText(
            "<span style='color:#2e7d32;'>✅ msal instalado com sucesso!<br>"
            "<b>Reinicie o QGIS</b> e clique em Login novamente.</span>"
        )
        self._btn_install.setVisible(False)

    def _on_install_failed(self, _pkg: str, _error: str):
        self._install_progress.setVisible(False)
        self._install_status.setText(
            "<span style='color:#d93025;'>❌ Falha na instalação automática.<br>"
            "Abra o <b>OSGeo4W Shell</b> e execute:<br>"
            "<code>pip install msal</code></span>"
        )
        self._btn_install.setEnabled(True)

    # ------------------------------------------------------------------
    # Getters - usar após exec_() retornar Accepted
    # ------------------------------------------------------------------

    def get_provider(self) -> EntraAuthProvider:
        return self._provider

    def get_session(self):
        if self._provider and self._provider.is_authenticated():
            return self._provider.get_session()
        return None

    def get_username(self) -> str:
        if self._provider:
            return self._provider.get_username()
        return ""

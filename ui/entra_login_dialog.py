# -*- coding: utf-8 -*-
"""
entra_login_dialog.py — GeoMetadata Plugin
===========================================
Diálogo de login via Microsoft Entra ID (OAuth2 + PKCE).

Executa a autenticação em QThread para não bloquear a UI do QGIS.
O msal.acquire_token_interactive() abre o navegador padrão do sistema
e aguarda o callback no localhost.

Autor: GeoMetadata Plugin | CDHU
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QWidget, QMessageBox, QSizePolicy
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QSize
from qgis.PyQt.QtGui import QIcon, QFont

from ..core.entra_auth_provider import EntraAuthProvider, is_msal_available, get_msal_install_instructions


# ---------------------------------------------------------------------------
# Worker — roda a autenticação MSAL em thread separada
# ---------------------------------------------------------------------------
class _AuthWorker(QThread):
    """
    Executa acquire_token_interactive() em background para não travar a UI.
    Emite auth_success(provider) ou auth_failed(error_msg).
    """
    auth_success = pyqtSignal(object)   # EntraAuthProvider
    auth_failed  = pyqtSignal(str)      # mensagem de erro

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


# ---------------------------------------------------------------------------
# EntraLoginDialog — janela de login
# ---------------------------------------------------------------------------
class EntraLoginDialog(QDialog):
    """
    Diálogo de login via Microsoft Entra ID.

    Após exec_() bem-sucedido (retorna QDialog.Accepted):
        provider = dialog.get_provider()   # EntraAuthProvider autenticado
        session  = dialog.get_session()    # requests.Session com Bearer Token
        username = dialog.get_username()   # nome do usuário logado
    """

    def __init__(self, client_id: str, tenant_id: str, scopes: list, parent=None):
        super().__init__(parent)
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._scopes = scopes
        self._provider = None
        self._worker = None

        self._build_ui()
        self.setWindowTitle("Entrar com conta CDHU")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        # --- Ícone + Título ---
        title_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(
            QIcon(":/plugins/geometadata/img/header_logo.png")
            .pixmap(QSize(120, 40))
        )
        title_layout.addWidget(icon_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # --- Descrição ---
        desc = QLabel(
            "<p style='font-size:13px;'>"
            "Clique em <b>Entrar</b> para autenticar com sua conta corporativa.<br>"
            "O navegador padrão será aberto automaticamente."
            "</p>"
        )
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.RichText)
        layout.addWidget(desc)

        # --- Status / Progress ---
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setTextFormat(Qt.RichText)
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminado
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        layout.addWidget(self._progress)

        # --- Botões ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_cancel = QPushButton("Cancelar")
        self._btn_cancel.clicked.connect(self._on_cancel)

        self._btn_login = QPushButton("⬛  Entrar com conta CDHU")
        self._btn_login.setDefault(True)
        self._btn_login.setMinimumWidth(200)
        self._btn_login.clicked.connect(self._start_auth)

        btn_layout.addWidget(self._btn_cancel)
        btn_layout.addWidget(self._btn_login)
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # Lógica de autenticação
    # ------------------------------------------------------------------

    def _start_auth(self):
        """Verifica pré-requisitos e inicia o fluxo de autenticação."""
        # Verificar dependência msal
        if not is_msal_available():
            QMessageBox.critical(
                self, "Dependência não encontrada",
                get_msal_install_instructions()
            )
            return

        # UI: aguardando
        self._set_waiting_state(True)
        self._status_label.setText(
            "<span style='color:#1a73e8;'>🌐 Aguardando login no navegador...</span>"
        )

        # Criar provider e worker
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
        """Chamado quando a autenticação MSAL retorna com sucesso."""
        self._set_waiting_state(False)
        self._provider = provider
        self.accept()   # fecha o diálogo com QDialog.Accepted

    def _on_auth_failed(self, error_msg: str):
        """Chamado quando a autenticação falha ou é cancelada."""
        self._set_waiting_state(False)
        self._status_label.setText(
            f"<span style='color:#d93025;'>❌ {error_msg}</span>"
        )

    def _on_cancel(self):
        """Cancela a operação. Se um worker estiver rodando, aguarda encerramento."""
        if self._worker and self._worker.isRunning():
            # Não há como forçar interrupção do msal (está no browser do usuário)
            # O worker terminará naturalmente quando o usuário fechar o browser ou timeout
            self._worker.quit()
        self.reject()

    def _set_waiting_state(self, waiting: bool):
        """Alterna o estado visual entre idle e aguardando."""
        self._btn_login.setEnabled(not waiting)
        self._progress.setVisible(waiting)
        if not waiting:
            self._status_label.setText("")

    # ------------------------------------------------------------------
    # Getters — usar após exec_() retornar Accepted
    # ------------------------------------------------------------------

    def get_provider(self) -> EntraAuthProvider:
        """Retorna o EntraAuthProvider autenticado."""
        return self._provider

    def get_session(self):
        """Retorna uma requests.Session com Bearer Token injetado."""
        if self._provider and self._provider.is_authenticated():
            return self._provider.get_session()
        return None

    def get_username(self) -> str:
        """Retorna o nome/e-mail do usuário autenticado."""
        if self._provider:
            return self._provider.get_username()
        return ""

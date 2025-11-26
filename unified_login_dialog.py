# unified_login_dialog.py
import os
import requests
from qgis.PyQt import uic, QtWidgets
from qgis.core import Qgis, QgsApplication
from qgis.gui import QgsAuthConfigSelect
from .plugin_config import config_loader

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'unified_login_dialog_base.ui'))

class UnifiedLoginDialog(QtWidgets.QDialog, FORM_CLASS):
    """
    Diálogo de autenticação unificado, seguindo o padrão das janelas de conexão do QGIS.
    """
    def __init__(self, parent=None, iface=None):
        super(UnifiedLoginDialog, self).__init__(parent)
        self.setupUi(self)
        self.iface = iface
        
        self.authenticated_session = None
        self.username = None

        # --- CRIA O WIDGET DE SELEÇÃO DE AUTENTICAÇÃO ---
        self.auth_select = QgsAuthConfigSelect(self, "gdal")
        
        # --- INJETA O WIDGET NO LAYOUT DO CONTÊINER ---
        # Busca o layout que acabamos de criar para o nosso widget contêiner no Qt Designer.
        container_layout = self.saveCredentialsGroup.layout()
        
        # Adiciona o seletor de autenticação a esse layout.
        if container_layout is not None:
            container_layout.addWidget(self.auth_select)
            # Remove as margens para que ele preencha o espaço perfeitamente
            container_layout.setContentsMargins(0, 0, 0, 0)
        else:
            print("AVISO CRÍTICO: O 'authContainerWidget' no .ui não tem um layout aplicado!")
            # Como plano B, podemos criar um aqui, mas o ideal é fazer no Designer
            layout = QtWidgets.QVBoxLayout(self.saveCredentialsGroup)
            layout.setContentsMargins(2, 10, 2, 0)
            layout.addWidget(self.auth_select)

        # --- LÓGICA DE UI (Robusta) ---
        if hasattr(self.auth_select, 'configChanged'):
            self.auth_select.configChanged.connect(self.on_auth_config_changed)
        elif hasattr(self.auth_select, 'changed'):
            self.auth_select.changed.connect(self.on_auth_config_changed)

        self.on_auth_config_changed()

    def on_auth_config_changed(self):
        """
        Ativado quando o usuário seleciona uma configuração diferente.
        Desabilita a entrada manual se uma configuração for selecionada.
        """
        config_id = self.auth_select.configId()
        is_config_selected = bool(config_id)
        
        self.basicCredentialsGroup.setEnabled(not is_config_selected)
        
        if is_config_selected:
            self.lineEdit_user.clear()
            self.lineEdit_password.clear()

    def accept(self):
        """
        Sobrescreve o botão OK para obter credenciais da fonte correta.
        """
        geoserver_url = config_loader.get_geoserver_url()
        # ... (código de verificação da URL) ...

        user = None
        password = None
        
        config_id = self.auth_select.configId()
        
        if config_id:
            # --- MODO CONFIGURAÇÃO SALVA ---
            auth_manager = QgsApplication.authManager()
            config_obj = auth_manager.availableAuthMethodConfigs().get(config_id)
            if not config_obj or not auth_manager.loadAuthenticationConfig(config_id, config_obj, True):
                QtWidgets.QMessageBox.critical(self, "Falha ao Carregar", "Não foi possível carregar a configuração.")
                return
            
            credentials = config_obj.configMap()
            user = credentials.get('username')
            password = credentials.get('password')
            self.username = user

        else:
            # --- MODO ENTRADA MANUAL ---
            user = self.lineEdit_user.text()
            password = self.lineEdit_password.text()
            if not all([user, password]):
                QtWidgets.QMessageBox.warning(self, "Campos Incompletos", "Usuário e senha são obrigatórios.")
                return
            self.username = user

        # --- LÓGICA DE AUTENTICAÇÃO (COMUM A AMBOS OS MODOS) ---
        if not all([user, password]):
            QtWidgets.QMessageBox.critical(self, "Erro", "Não foi possível obter as credenciais.")
            return

        session = requests.Session()
        session.verify = False        
        session.auth = (user, password)
        test_url = f"{geoserver_url}/ows?version=1.3.0"
        
        try:
            response = session.get(test_url, timeout=15, verify=False)
            response.raise_for_status()
            
            self.authenticated_session = session
            super().accept()

        except requests.exceptions.HTTPError as e:
            msg = "Usuário ou senha inválidos." if e.response.status_code == 401 else f"<p>Erro do servidor: {e}</p><p>Contate a equipe de TI via chamado no CDA!</p>"
            QtWidgets.QMessageBox.critical(self, "Falha na Autenticação", msg)
        except requests.exceptions.RequestException as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Não foi possível conectar: {e}")

    def get_session(self):
        return self.authenticated_session
        
    def get_username(self):
        return self.username
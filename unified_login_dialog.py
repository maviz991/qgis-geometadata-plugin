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

        # --- CRIA E INJETA O WIDGET DE SELEÇÃO DE AUTENTICAÇÃO ---
        self.auth_select = QgsAuthConfigSelect(self, "gdal")
        
        # Cria um layout para o nosso widget contêiner e adiciona o seletor de auth
        layout = QtWidgets.QVBoxLayout(self.authContainerWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.auth_select)

        # --- LÓGICA DE UI ---
        # Conecta o sinal do seletor a uma função que habilita/desabilita o groupbox
        self.auth_select.configChanged.connect(self.on_auth_config_changed)
        
        # Chama a função uma vez no início para definir o estado inicial correto
        self.on_auth_config_changed()

    def on_auth_config_changed(self):
        """
        Ativado quando o usuário seleciona uma configuração diferente no ComboBox.
        Desabilita a entrada manual se uma configuração for selecionada.
        """
        config_id = self.auth_select.configId()
        is_config_selected = bool(config_id)
        
        # Habilita ou desabilita o GroupBox de credenciais básicas
        self.basicCredentialsGroup.setEnabled(not is_config_selected)
        
        # Limpa os campos de texto se uma config for selecionada, para evitar confusão
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
        session.auth = (user, password)
        session.verify = False
        test_url = f"{geoserver_url}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
        
        try:
            response = session.get(test_url, timeout=15)
            response.raise_for_status()
            
            self.authenticated_session = session
            super().accept()

        except requests.exceptions.HTTPError as e:
            msg = "Usuário ou senha inválidos." if e.response.status_code == 401 else f"Erro do servidor: {e}"
            QtWidgets.QMessageBox.critical(self, "Falha na Autenticação", msg)
        except requests.exceptions.RequestException as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Não foi possível conectar: {e}")

    def get_session(self):
        return self.authenticated_session
        
    def get_username(self):
        return self.username
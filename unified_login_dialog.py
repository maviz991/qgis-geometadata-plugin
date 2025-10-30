# unified_login_dialog.py
import os
import requests
from qgis.PyQt import uic, QtWidgets
from qgis.core import Qgis, QgsApplication
# Importa o widget de seleção de autenticação que você encontrou!
from qgis.gui import QgsAuthConfigSelect
from .plugin_config import config_loader

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'unified_login_dialog_base.ui'))

class UnifiedLoginDialog(QtWidgets.QDialog, FORM_CLASS):
    """
    Diálogo de autenticação com abas, permitindo seleção de configuração
    salva ou entrada de credenciais básicas.
    """
    def __init__(self, parent=None, iface=None):
        super(UnifiedLoginDialog, self).__init__(parent)
        self.setupUi(self)
        self.iface = iface
        
        self.authenticated_session = None
        self.username = None # Para armazenar o nome de usuário para a UI

        # --- CRIA E INJETA O WIDGET DE SELEÇÃO DE AUTENTICAÇÃO ---
        # "gdal" é um provedor que usa autenticação básica, o que filtra a lista
        # para mostrar apenas as configurações relevantes.
        self.auth_select = QgsAuthConfigSelect(self, "gdal")
        
        # Encontra o layout dentro da primeira aba e adiciona o widget
        # Supondo que o layout se chame 'verticalLayout' dentro da aba 'tabConfig'
        self.tabConfig.layout().addWidget(self.auth_select)

    def accept(self):
        """
        Sobrescreve o botão OK para lidar com a lógica de ambas as abas.
        """
        geoserver_url = config_loader.get_geoserver_url()
        if not geoserver_url:
            self.iface.messageBar().pushMessage("Erro", "URL do GeoServer não definida.", level=Qgis.Critical)
            return

        user = None
        password = None

        # --- LÓGICA DE ABAS ---
        # Verifica qual aba está atualmente selecionada
        if self.tabWidget.currentWidget() == self.tabBasic:
            # --- Aba Básico ---
            user = self.lineEdit_user.text()
            password = self.lineEdit_password.text()
            if not all([user, password]):
                QtWidgets.QMessageBox.warning(self, "Campos Incompletos", "Usuário e senha são obrigatórios.")
                return
            self.username = user # Salva o nome de usuário para a UI

        elif self.tabWidget.currentWidget() == self.tabConfig:
            # --- Aba Configurações ---
            auth_cfg_id = self.auth_select.configId()
            if not auth_cfg_id:
                QtWidgets.QMessageBox.warning(self, "Seleção Necessária", "Por favor, selecione uma configuração de autenticação.")
                return

            auth_manager = QgsApplication.authManager()
            # O método loadAuthenticationConfig preenche um objeto existente
            config_obj = auth_manager.availableAuthMethodConfigs().get(auth_cfg_id)
            if not config_obj or not auth_manager.loadAuthenticationConfig(auth_cfg_id, config_obj, True):
                QtWidgets.QMessageBox.critical(self, "Falha ao Carregar", "Não foi possível carregar a configuração. Verifique sua senha mestra.")
                return
            
            credentials = config_obj.configMap()
            user = credentials.get('username')
            password = credentials.get('password')
            self.username = user # Salva o nome de usuário para a UI

        # --- LÓGICA DE AUTENTICAÇÃO (COMUM A AMBAS AS ABAS) ---
        if not all([user, password]):
            # Este erro só deve acontecer se algo muito errado ocorrer
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
            super().accept() # Fecha o diálogo com sucesso

        except requests.exceptions.HTTPError as e:
            msg = "Usuário ou senha inválidos." if e.response.status_code == 401 else f"Erro do servidor: {e}"
            QtWidgets.QMessageBox.critical(self, "Falha na Autenticação", msg)
        except requests.exceptions.RequestException as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Não foi possível conectar: {e}")

    def get_session(self):
        """Retorna a sessão autenticada."""
        return self.authenticated_session
        
    def get_username(self):
        """Retorna o nome de usuário para ser exibido na UI principal."""
        return self.username
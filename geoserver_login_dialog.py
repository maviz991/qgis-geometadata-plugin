# geoserver_login_dialog.py
import os
import requests
from qgis.PyQt import uic, QtWidgets
from .plugin_config import config_loader

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'geoserver_login_dialog_base.ui')) #para que o user coloque o url

class GeoServerLoginDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(GeoServerLoginDialog, self).__init__(parent)
        self.setupUi(self)
        self.credentials = None
        # Definimos a URL a partir da configuração ao inicializar

    # FUNÇÃO DE PREENCHIMENTO DOS DADOS DE CAMADAS PERSISTENTE
    def set_data(self, data):
            """Pré-preenche os campos com dados existentes."""
            if not data:
                return
            # Lembra do último nome de usuário digitado
            self.lineEdit_username.setText(data.get('geoserver_user', ''))

    def accept(self):
        """ Sobrescreve o comportamento do botão OK/Login. """
        url = config_loader.get_geoserver_url()
        user = self.lineEdit_username.text()
        password = self.lineEdit_password.text()

        if not all([user, password]):
            QtWidgets.QMessageBox.warning(self, "Campos Incompletos", "Todos os campos são obrigatórios.")
            return
        
        if not url:
            QtWidgets.QMessageBox.critical(self, "Erro de Configuração", "A URL do GeoServer não está definida no arquivo config.json do plugin.")
            return
        
        # Tenta uma requisição simples (WMS GetCapabilities) para validar
        test_url = f"{url}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
        try:
            response = requests.get(test_url, auth=(user, password), timeout=15, verify=False)
            response.raise_for_status() # Lança um erro para status 4xx ou 5xx
            
            # Se chegou aqui, o login foi bem-sucedido
            self.credentials = {'url': url, 'user': user, 'password': password, 'geoserver_user': user}
            super().accept() # Fecha o diálogo com status "Aceito"

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                QtWidgets.QMessageBox.critical(self, "Falha na Autenticação", "Usuário ou senha inválidos.")
            else:
                QtWidgets.QMessageBox.critical(self, "Erro de Servidor", f"O servidor respondeu com um erro: {e}")
        except requests.exceptions.RequestException as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Não foi possível conectar ao GeoServer: {e}")

    def get_credentials(self):
        creds = self.credentials
        if creds:
            creds['geoserver_user'] = creds.get('user')
        return creds
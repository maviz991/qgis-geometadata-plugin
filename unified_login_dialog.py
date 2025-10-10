# unified_login_dialog.py
import os
import requests
from qgis.PyQt import uic, QtWidgets
from qgis.core import Qgis
from .plugin_config import config_loader

# Certifique-se de que o nome do arquivo .ui aqui corresponde ao seu arquivo renomeado
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'unified_login_dialog_base.ui'))

class UnifiedLoginDialog(QtWidgets.QDialog, FORM_CLASS):
    """
    Uma dialog unificada para autenticar no portal e criar uma sessão reutilizável.
    """
    def __init__(self, parent=None):
        super(UnifiedLoginDialog, self).__init__(parent)
        self.setupUi(self)
        self.authenticated_session = None
        self.last_username = None

    def set_data(self, data):
        """Pré-preenche o campo de usuário com o último valor usado."""
        if data and 'last_username' in data:
            self.lineEdit_username.setText(data.get('last_username', ''))

    def accept(self):
        """
        Sobrescreve o botão OK. Tenta autenticar, cria uma sessão e a armazena.
        """
        geoserver_url = config_loader.get_geoserver_url()
        user = self.lineEdit_username.text()
        password = self.lineEdit_password.text()

        if not all([user, password]):
            QtWidgets.QMessageBox.warning(self, "Campos Incompletos", "Usuário e senha são obrigatórios.")
            return
        
        if not geoserver_url:
            self.iface.messageBar().pushMessage("Erro", "A URL do GeoServer não está definida no arquivo de configuração do plugin.", level=Qgis.Critical)
            return
        
        # 1. Criar um objeto de sessão que irá armazenar os cookies
        session = requests.Session()
        
        # 2. Configurar a autenticação básica para todas as requisições nesta sessão
        session.auth = (user, password)
        session.verify = False # Manter para certificados autoassinados, se necessário

        # 3. Tentar uma requisição para validar as credenciais e obter o cookie de sessão
        # A URL do GetCapabilities do GeoServer é um ótimo alvo para isso
        test_url = f"{geoserver_url}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
        
        try:
            # Usamos o objeto session para a requisição. Ele automaticamente lida com a autenticação.
            response = session.get(test_url, timeout=15)
            response.raise_for_status() # Lança um erro para status 4xx ou 5xx
            
            # Se chegou aqui, a autenticação funcionou e a sessão agora contém o cookie.
            # Armazenamos a sessão autenticada para ser usada pelo resto do plugin.
            self.authenticated_session = session
            self.last_username = user # Salvar para a próxima vez
            
            super().accept() # Fecha o diálogo com status "Aceito"

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                QtWidgets.QMessageBox.critical(self, "Falha na Autenticação", "Usuário ou senha inválidos.")
            else:
                QtWidgets.QMessageBox.critical(self, "Erro de Servidor", f"O servidor respondeu com um erro: {e}")
        except requests.exceptions.RequestException as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Não foi possível conectar ao portal: {e}")

    def get_session(self):
        """Retorna a sessão autenticada."""
        return self.authenticated_session
        
    def get_last_username(self):
        """Retorna o nome de usuário para persistência."""
        return self.last_username
# unified_login_dialog.py
import os
import requests
from qgis.PyQt import uic, QtWidgets
# NÃO importamos mais QgsAuthenticationConfig
from qgis.core import Qgis, QgsApplication
from .plugin_config import config_loader

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'unified_login_dialog_base.ui'))

class UnifiedLoginDialog(QtWidgets.QDialog, FORM_CLASS):
    """
    Diálogo de login que usa o Gerenciador de Autenticação do QGIS.
    Compatível com a API do QGIS 3.4 LTR.
    """
    def __init__(self, parent=None, iface=None):
        super(UnifiedLoginDialog, self).__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.authenticated_session = None
        self.selected_auth_cfg_id = None
        self.auth_manager = QgsApplication.authManager()
        self.signal_name_to_disconnect = None
        
        # Carregamos o mapa de configurações uma vez para reutilização
        self.auth_configs_map = self.auth_manager.availableAuthMethodConfigs()

        self.mManageAuthButton.clicked.connect(self.open_auth_settings)
        
        # Conecta ao sinal correto para esta versão da API
        if hasattr(self.auth_manager, 'authDatabaseChanged'):
            self.auth_manager.authDatabaseChanged.connect(self.populate_auth_combobox)
            self.signal_name_to_disconnect = 'authDatabaseChanged'
            print("INFO: Conectado ao sinal 'authDatabaseChanged'.")
        else:
            print("AVISO: Não foi possível conectar ao sinal de mudança de configuração.")
        
        self.populate_auth_combobox()

    def populate_auth_combobox(self):
        """Preenche a QComboBox com as configurações de autenticação disponíveis."""
        current_selection = self.mAuthComboBox.currentData()
        self.mAuthComboBox.clear()
        
        # Atualiza o mapa de configs caso tenha mudado
        self.auth_configs_map = self.auth_manager.availableAuthMethodConfigs()
        
        if not self.auth_configs_map:
            self.mAuthComboBox.addItem("Nenhuma configuração encontrada")
            self.mAuthComboBox.setEnabled(False)
            return

        self.mAuthComboBox.setEnabled(True)
        index_to_set = 0
        
        for i, (config_id, config_obj) in enumerate(self.auth_configs_map.items()):
            self.mAuthComboBox.addItem(config_obj.name(), config_id)
            if config_id == current_selection:
                index_to_set = i
        
        self.mAuthComboBox.setCurrentIndex(index_to_set)

    def open_auth_settings(self):
        """
        Abre o diálogo de opções do QGIS na aba de Autenticação,
        usando o método compatível com a versão do QGIS.
        """
        if hasattr(QgsApplication, 'showOptionsDialog'):
            # Método moderno (QGIS 3.10+)
            QgsApplication.showOptionsDialog(parent=self, currentPage='mAuthOptionsPage')
        elif self.iface and hasattr(self.iface, 'showOptionsDialog'):
            # Método legado (QGIS 3.4)
            self.iface.showOptionsDialog(parent=self, page='authentication')
        else:
            QtWidgets.QMessageBox.warning(self, "Não é possível abrir",
                                        "Não foi possível encontrar um método para abrir as opções de autenticação.")

    def accept(self):
        """Obtém as credenciais da configuração selecionada e tenta autenticar."""
        geoserver_url = config_loader.get_geoserver_url()
        if not geoserver_url:
            # ... (código de erro)
            return

        auth_cfg_id = self.mAuthComboBox.currentData()
        if not auth_cfg_id:
            QtWidgets.QMessageBox.warning(self, "Autenticação Necessária", "Por favor, selecione ou crie uma configuração.")
            return
            
        self.selected_auth_cfg_id = auth_cfg_id

        # --- LÓGICA FINAL CORRETA ---
        # 1. Obtenha o objeto de configuração (base) do nosso mapa
        auth_config = self.auth_configs_map.get(self.selected_auth_cfg_id)
        if not auth_config:
            QtWidgets.QMessageBox.critical(self, "Erro Interno", "A configuração selecionada não foi encontrada.")
            return

        # 2. Passe este objeto para ser preenchido com os dados descriptografados
        if not self.auth_manager.loadAuthenticationConfig(self.selected_auth_cfg_id, auth_config, True):
            QtWidgets.QMessageBox.critical(self, "Falha ao Carregar", "Não foi possível carregar os detalhes da configuração.")
            return

        # 3. Verifique se é válido (pode precisar da senha mestra)
        if not auth_config.isValid():
            if hasattr(self.auth_manager, 'initAuthentication'):
                self.auth_manager.initAuthentication(self.selected_auth_cfg_id)
                # Tente recarregar após a possível entrada da senha mestra
                self.auth_manager.loadAuthenticationConfig(self.selected_auth_cfg_id, auth_config, True)
            
            if not auth_config.isValid():
                QtWidgets.QMessageBox.critical(self, "Falha na Autenticação", "Não foi possível validar a configuração. Verifique sua senha mestra.")
                return

        credentials = auth_config.configMap()
        user = credentials.get('username')
        password = credentials.get('password')

        if not all([user, password]):
            QtWidgets.QMessageBox.critical(self, "Configuração Incompleta", "A configuração selecionada não possui usuário e/ou senha.")
            return

        # O resto do código permanece o mesmo...
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
            msg = f"As credenciais da configuração '{auth_config.name()}' são inválidas." if e.response.status_code == 401 else f"O servidor respondeu com um erro: {e}"
            QtWidgets.QMessageBox.critical(self, "Falha na Autenticação", msg)
        except requests.exceptions.RequestException as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Não foi possível conectar ao portal: {e}")

    def get_session(self):
        return self.authenticated_session

    def get_selected_auth_cfg_id(self):
        return self.selected_auth_cfg_id

    def closeEvent(self, event):
        """Desconecta o sinal quando a janela for fechada."""
        if self.signal_name_to_disconnect:
            try:
                signal_instance = getattr(self.auth_manager, self.signal_name_to_disconnect)
                signal_instance.disconnect(self.populate_auth_combobox)
                print(f"INFO: Desconectado do sinal '{self.signal_name_to_disconnect}'.")
            except Exception as e:
                print(f"AVISO: Falha ao desconectar o sinal '{self.signal_name_to_disconnect}': {e}")
        super(UnifiedLoginDialog, self).closeEvent(event)
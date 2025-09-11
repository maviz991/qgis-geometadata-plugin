import os
from qgis.PyQt import uic, QtWidgets

# ---------------------------- TELA DE LOGIN --------------------------- 
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'login_dialog_base.ui'))

class LoginDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(LoginDialog, self).__init__(parent)
        self.setupUi(self)
        
    def getCredentials(self):
        """Retorna o usuário e a senha inseridos."""
        # Acessa os widgets pelo objectName que definimos no Designer
        username = self.lineEdit_username.text()
        password = self.lineEdit_password.text()
        return (username, password)
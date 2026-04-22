import re

with open('GeoMetadata_dialog.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update _create_header
old_header = r'''        # --- CRIAÇÃO E CONFIGURAÇÃO DOS BOTÕES ---.*?        # --- Montagem do Layout ---'''
new_header = '''        # --- CRIAÇÃO E CONFIGURAÇÃO DOS BOTÕES (ESTILO MENU WEB) ---
        from qgis.PyQt.QtWidgets import QMenu, QPushButton
        
        # --- MENU: ARQUIVO ---
        self.btn_menu_arquivo = QPushButton("Opções ▾")
        self.btn_menu_arquivo.setObjectName("HeaderMenuButton")
        self.btn_menu_arquivo.setCursor(Qt.PointingHandCursor)
        self.menu_arquivo = QMenu(self.btn_menu_arquivo)
        self.action_salvar = self.menu_arquivo.addAction("Continuar depois (Salvar rascunho)")
        self.action_exp_xml = self.menu_arquivo.addAction("Exportar Metadado para XML")
        self.btn_menu_arquivo.setMenu(self.menu_arquivo)

        # --- MENU: GEOHAB ---
        self.btn_menu_geohab = QPushButton("Geohab ▾")
        self.btn_menu_geohab.setObjectName("HeaderMenuButton")
        self.btn_menu_geohab.setCursor(Qt.PointingHandCursor)
        self.menu_geohab = QMenu(self.btn_menu_geohab)
        self.action_associar = self.menu_geohab.addAction("Associar Camada WMS/WFS")
        self.action_exp_geo = self.menu_geohab.addAction("Publicar Metadado no Geohab")
        self.btn_menu_geohab.setMenu(self.menu_geohab)

        # Botão "Entrar" (Login)
        self.header_btn_login = QPushButton()
        self.header_btn_login.setObjectName("ConnectButton")
        self.header_btn_login.setCursor(Qt.PointingHandCursor)

        # --- Montagem do Layout ---'''

content = re.sub(old_header, new_header, content, flags=re.DOTALL)

# 2. Update _setup_button_connections
old_conns = r'''    def _setup_button_connections\(self\):.*?        self\.header_btn_login\.clicked\.connect\(self\.authenticate\)'''
new_conns = '''    def _setup_button_connections(self):
        """Conecta as ações dos menus dropdown aos callbacks."""
        self.action_exp_xml.triggered.connect(self.exportar_to_xml)
        self.action_salvar.triggered.connect(lambda: self.save_metadata(is_automatic_resave=False))
        self.action_exp_geo.triggered.connect(self.exportar_to_geo)
        self.action_associar.triggered.connect(self.open_distribution_workflow)
        self.header_btn_login.clicked.connect(self.authenticate)'''

content = re.sub(old_conns, new_conns, content, flags=re.DOTALL)

# 3. Update update_ui_for_login_status
content = content.replace('self.header_btn_exp_geo.setEnabled(is_logged_in)', 'self.action_exp_geo.setEnabled(is_logged_in)')
content = content.replace('self.header_btn_distribution_info.setEnabled(is_logged_in)', 'self.action_associar.setEnabled(is_logged_in)')

with open('GeoMetadata_dialog.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Header dropdown menus updated successfully in Python.")

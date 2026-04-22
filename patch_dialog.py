import re

with open('GeoMetadata_dialog.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add imports
imports = '''from .core import xml_generator, xml_parser
from .ui.form_manager import FormManager
from .core.metadata_service import MetadataService
from .core.persistence_service import PersistenceService'''
content = content.replace('from .core import xml_generator, xml_parser', imports)

# Modify __init__ to instantiate services
init_add = '''        self.metadata_service = MetadataService(self.plugin.api_session)
        self.persistence_service = PersistenceService(self.iface)
        self.form_manager = FormManager(self.ui, self, self.contatos_predefinidos)'''
content = content.replace('self._load_contacts()', 'self._load_contacts()\n' + init_add)

# Replace _setup_connections_and_logic
old_setup = '''    def _setup_connections_and_logic(self):
        """Conecta os sinais dos widgets e inicializa a lógica da UI."""
        self._setup_button_connections()
        self._setup_login_icons()
        self.populate_comboboxes()
        self.update_ui_for_login_status()
        self.auto_fill_from_layer()
        self.update_distribution_display()
        self.form_is_dirty = False
        #print("Formulário carregado. Dirty flag resetada para False.") # Para debug
        self._connect_dirty_flag_signals()'''

new_setup = '''    def _setup_connections_and_logic(self):
        """Conecta os sinais dos widgets e inicializa a lógica da UI."""
        self._setup_button_connections()
        self._setup_login_icons()
        self.update_ui_for_login_status()
        self.auto_fill_from_layer()
        self.update_distribution_display()
        self.form_manager.connect_dirty_signals(self.on_metadata_changed)

    def on_metadata_changed(self):
        pass # Optional logic when metadata becomes dirty'''
        
content = content.replace(old_setup, new_setup)

# Change comboboxes connect
content = content.replace('self.ui.comboBox_contact_presets.currentIndexChanged.connect(self.on_contact_preset_changed)', 'self.ui.comboBox_contact_presets.currentIndexChanged.connect(self.form_manager.on_contact_preset_changed)')

# Update references to collect_data
content = content.replace('self.collect_data()', 'self.form_manager.collect_data()')

# Substitute exporting and saving methods
auto_fill = '''    def auto_fill_from_layer(self):
        """Tenta preencher o formulário usando os metadados associados à camada."""
        layer = self.iface.activeLayer()
        if not layer:
            return
            
        xml_content = self.persistence_service.load(layer)
        if xml_content:
            data_dict = xml_parser.parse_xml_to_dict(xml_content, is_string=True)
            self.form_manager.populate_form_from_dict(data_dict)
            self.form_manager.set_is_dirty(False)
            
        self.update_distribution_display()'''

# regex replace auto_fill_from_layer body
content = re.sub(r'    def auto_fill_from_layer\(self\):.*?    def _is_postgres_layer', auto_fill + '\n\n    def _is_postgres_layer', content, flags=re.DOTALL)

with open('GeoMetadata_dialog.py', 'w', encoding='utf-8') as f:
    f.write(content)

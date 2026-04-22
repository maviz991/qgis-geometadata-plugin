import re
with open('GeoMetadata_dialog.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace exportar_to_geo body
export_new = '''    def exportar_to_geo(self):
        """Exporta para o GeoNetwork usando o MetadataService."""
        if not self.form_manager.validate_form(): return
        if not self.plugin.api_session:
            QtWidgets.QMessageBox.warning(self, 'Não Autenticado', 'Conecte ao Geohab primeiro.')
            return
            
        metadata_dict = self.form_manager.collect_data()
        reply = QtWidgets.QMessageBox.question(self, 'Confirmar', f"Exportar {metadata_dict.get('title')}?", QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        if reply != QtWidgets.QMessageBox.Ok: return
        
        try:
            template_path = os.path.join(os.path.dirname(__file__), 'assets', 'tamplate_mgb20.xml')
            cdhu_data = self.contatos_predefinidos.get('cdhu', {})
            import os
            from .core import xml_generator
            xml_payload = xml_generator.generate_xml_from_template(metadata_dict, template_path, cdhu_data)
            
            from .core.plugin_config import config_loader
            uuid_criado = self.metadata_service.push_to_geonetwork(xml_payload, config_loader)
            
            if uuid_criado:
                self.form_manager.current_metadata_uuid = uuid_criado
                self.save_metadata(is_automatic_resave=True) # Salva sidecar atualizado
                QtWidgets.QMessageBox.information(self, 'Sucesso', f'Metadado exportado.\\nUUID: {uuid_criado}')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Erro', f'Falha no GeoNetwork: {e}')'''

content = re.sub(r'    def exportar_to_geo\(self\):.*?    def _translate_server_error\(self, error_text\):', export_new + '\n\n    def _translate_server_error(self, error_text):', content, flags=re.DOTALL)

# Delete translating server error and exportar to xml until save_metadata
content = re.sub(r'    def _translate_server_error\(self, error_text\):.*?    def save_metadata\(self, is_automatic_resave=False\):', '    def save_metadata(self, is_automatic_resave=False):', content, flags=re.DOTALL)

# Replace save metadata body
save_new = '''    def save_metadata(self, is_automatic_resave=False):
        """Usa o PersistenceService para salvar no DB ou XML Sidecar."""
        if not is_automatic_resave and not self.form_manager.validate_form(): return
        
        metadata_dict = self.form_manager.collect_data()
        layer = self.iface.activeLayer()
        import os
        template_path = os.path.join(os.path.dirname(__file__), 'assets', 'tamplate_mgb20.xml')
        cdhu_data = self.contatos_predefinidos.get('cdhu', {})
        
        success = self.persistence_service.save(layer, metadata_dict, template_path, cdhu_data, is_automatic_resave, self)
        if success:
            self.form_manager.set_is_dirty(False)'''

content = re.sub(r'    def save_metadata\(self, is_automatic_resave=False\):.*?    def sanitize_title\(self', save_new + '\n\n    def sanitize_title(self', content, flags=re.DOTALL)

# And remove everything from _is_postgres_layer up to update_distribution_display
content = re.sub(r'    def _is_postgres_layer\(self, layer\):.*?    def update_distribution_display\(self\):', '    def update_distribution_display(self):', content, flags=re.DOTALL)

with open('GeoMetadata_dialog.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Patch 3 applied successfully')

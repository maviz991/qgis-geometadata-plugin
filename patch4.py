import re
with open('GeoMetadata_dialog.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add exportar_to_xml
exportar_xml = '''    def exportar_to_xml(self):
        """Gera o XML e permite salvar no disco manual."""
        if not self.form_manager.validate_form(): return
        
        metadata_dict = self.form_manager.collect_data()
        try:
            import os
            from .core import xml_generator
            from qgis.PyQt import QtWidgets
            template_path = os.path.join(os.path.dirname(__file__), 'assets', 'tamplate_mgb20.xml')
            cdhu_data = self.contatos_predefinidos.get('cdhu', {})
            xml_payload = xml_generator.generate_xml_from_template(metadata_dict, template_path, cdhu_data)
            
            safe_filename = metadata_dict.get('title', 'metadados').replace(' ', '_') + '.xml'
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Salvar Metadados XML', safe_filename, 'Arquivos XML (*.xml)')
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(xml_payload)
                self.iface.messageBar().pushMessage('Sucesso', f'Metadados salvos em: {file_path}', level=1, duration=5)
        except Exception as e:
            from qgis.PyQt import QtWidgets
            QtWidgets.QMessageBox.critical(self, 'Erro', f'Falha ao exportar XML: {e}')'''

content = re.sub(r'    def exportar_to_geo\(self\):', exportar_xml + '\n\n    def exportar_to_geo(self):', content)
            
with open('GeoMetadata_dialog.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patch 4 applied')

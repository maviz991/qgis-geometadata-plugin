import sys

# 1. Update FormManager
with open('ui/form_manager.py', 'r', encoding='utf-8') as f:
    fm_content = f.read()

comboboxes_code = '''
    def populate_comboboxes(self):
        def populate(combo, options):
            combo.clear()
            for text, data in options:
                combo.addItem(text, data)
        
        populate(self.ui.comboBox_status_codeListValue, [('Arquivo Antigo', 'historicalArchive'), ('Concluído', 'completed'), ('Contínuo', 'onGoing'), ('Em Desenvolvimento', 'underDevelopment'), ('Necessário', 'required'), ('Obsoleto', 'obsolete'), ('Planejado', 'planned')])
        populate(self.ui.comboBox_contact_presets, [('CDHU', 'cdhu'), ('DPDU', 'dpdu'), ('SPHU', 'sphu'), ('SSARU', 'ssaru'), ('TERRAS', 'terras'), ('nenhum', 'nenhum')])
        populate(self.ui.comboBox_MD_SpatialRepresentationTypeCode, [('Vetor', 'vector'), ('Grid | Raster', 'grid'), ('Tabela de texto', 'textTable'), ('Rede triangular irregular (TIN)', 'tin'), ('Modelo estereofônico', 'stereoscopicModel'), ('Vídeo', 'video')])
        populate(self.ui.comboBox_LanguageCode, [('🇧🇷 Português', 'por'), ('🇺🇸 Inglês', 'eng'), ('🇪🇸 Espanhol', 'spa'), ('🇫🇷 Francês', 'fra'), ('🇩🇪 Alemão', 'ger')])
        populate(self.ui.comboBox_characterSet, [('UTF-8', 'utf8')])
        populate(self.ui.comboBox_topicCategory, [  ('Limites Administrativos', 'boundaries'), ('Planejamento e Cadastro', 'planningCadastre'), ('Sociedade e Cultura', 'society'), ('Infraestrutura ou Edificação', 'structure'), ('Transportes', 'transportation'), ('Localização', 'location'), ('Mapas ou imagens de Satélite', 'imageryBaseMapsEarthCover'), ('Altimetria, Batimetria ou Topografia', 'elevation'), ('Saúde', 'health'), ('Águas Interiores', 'inlandWaters'), ('Econômia', 'economy'), ('Biotipos', 'biota'), ('Climatologia ou Meteorologia', 'climatologyMeteorologyAtmosphere'), ('Informação GeoCientífica', 'geoscientificInformation'), ('Informação Militar', 'intelligenceMilitary'), ('Ambiente', 'environment'), ('Oceanos', 'oceans'), ('Infraestruturas de Comunicação', 'utilitiesCommunication'),  ('Agricultura, pesca ou pecuária', 'farming')])
        populate(self.ui.comboBox_hierarchyLevel, [('Conjunto de dados', 'dataset')])
        populate(self.ui.comboBox_contact_role, [('Dono', 'owner'), ('Autor', 'author'), ('Organizador', 'processor'), ('Distribuidor', 'distributor'), ('Depositário', 'custodian'), ('Fornecedor de recurso', 'resourceProvider'), ('Investigador principal', 'principalInvestigator'), ('Originador', 'originator'), ('Ponto de contato', 'pointOfContact'), ('Publicador', 'publisher'), ('Utilizador', 'user')])
        populate(self.ui.comboBox_contact_administrativeArea, [('São Paulo', 'SP'), ('Acre', 'AC'), ('Alagoas', 'AL'), ('Amapá', 'AP'), ('Amazonas', 'AM'), ('Bahia', 'BA'), ('Ceará', 'CE'), ('Distrito Federal', 'DF'), ('Espírito Santo', 'ES'), ('Goiás', 'GO'), ('Maranhão', 'MA'), ('Mato Grosso', 'MT'), ('Mato Grosso do Sul', 'MS'), ('Minas Gerais', 'MG'), ('Pará', 'PA'), ('Paraíba', 'PB'), ('Paraná', 'PR'), ('Pernambuco', 'PE'), ('Piauí', 'PI'), ('Rio de Janeiro', 'RJ'), ('Rio Grande do Norte', 'RN'), ('Rio Grande do Sul', 'RS'), ('Rondônia', 'RO'), ('Roraima', 'RR'), ('Santa Catarina', 'SC'), ('Sergipe', 'SE'), ('Tocantins', 'TO')])
'''

if 'def populate_comboboxes(self):' not in fm_content:
    fm_content = fm_content.replace('    def collect_data(self):', comboboxes_code + '\n    def collect_data(self):')
    with open('ui/form_manager.py', 'w', encoding='utf-8') as f:
        f.write(fm_content)

# 2. Update GeoMetadata_dialog.py
with open('GeoMetadata_dialog.py', 'r', encoding='utf-8') as f:
    dialog_content = f.read()

if 'self.form_manager.populate_comboboxes()' not in dialog_content:
    dialog_content = dialog_content.replace('self.update_ui_for_login_status()', 'self.form_manager.populate_comboboxes()\n        self.update_ui_for_login_status()')

close_events_code = '''
    def closeEvent(self, event):
        """Executado quando o usuário tenta fechar a janela."""
        if self.form_manager.get_is_dirty():
            from qgis.PyQt import QtWidgets
            reply = QtWidgets.QMessageBox.question(self, 
                                        'Alterações não Salvas',
                                        "Você tem alterações que não foram salvas.\\nDeseja realmente sair?",
                                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                        QtWidgets.QMessageBox.No)

            if reply == QtWidgets.QMessageBox.Yes:
                event.accept() 
            else:
                event.ignore() 
        else:
            event.accept()

    def reject(self):
        """Sobrescreve o comportamento padrão da tecla ESC."""
        self.close()
'''

if 'def closeEvent(self, event):' not in dialog_content:
    dialog_content += close_events_code
    
with open('GeoMetadata_dialog.py', 'w', encoding='utf-8') as f:
    f.write(dialog_content)

print('Patch applied: ComboBoxes and Window Events restored.')

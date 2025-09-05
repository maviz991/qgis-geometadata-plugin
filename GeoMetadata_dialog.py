# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GeoMetadataDialog
                                 A QGIS plugin
 Description
                             -------------------
        copyright            : (C) 2025 by Matheus Aviz
        email                : mdaviz@apoiocdhu.sp.gov.br
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from . import xml_generator
from qgis.core import Qgis


CONTATOS_PREDEFINIDOS = {
        'cdhu': {
            'contact_individualName': 'CDHU',
            'contact_organisationName': 'Companhia de Desenvolvimento Habitacional e Urbano',
            'contact_positionName': '/',
            'contact_phone': '+55 11 2505-2479',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé',
            'contact_city': 'São Paulo',
            'contact_postalCode': '01014-930',
            'contact_country': 'Brasil',
            'contact_email': 'geo@cdhu.sp.gov.br',
            'contact_administrativeArea': 'SP',
            'contact_role': 'owner'
        },
        'dpdu': {
            'contact_individualName': 'DPDU',
            'contact_organisationName': 'Diretoria de Planejamento e Desenvolvimento Urbano',
            'contact_positionName': '/',
            'contact_phone': '+55 11 2505-0000',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 9º andar',
            'contact_city': 'São Paulo',
            'contact_postalCode': '01014-930',
            'contact_country': 'Brasil',
            'contact_email': 'hub_habitacao@cdhu.sp.gov.br',
            'contact_administrativeArea': 'SP',
            'contact_role': 'processor'
        },
        'ssaru': {
            'contact_individualName': 'SSARU',
            'contact_organisationName': 'Superintendecia de Recuperação Social',
            'contact_positionName': '/',
            'contact_phone': '+55 11 2505-0000',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 7º andar',
            'contact_city': 'São Paulo',
            'contact_postalCode': '01014-930',
            'contact_country': 'Brasil',
            'contact_email': 'ssaru@cdhu.sp.gov.br',
            'contact_administrativeArea': 'SP',
            'contact_role': 'processor'
        },
        'nenhum': {
            'nenhum': {
            'contact_individualName': '',
            'contact_organisationName': '',
            'contact_positionName': '',
            'contact_phone': '',
            'contact_deliveryPoint': '',
            'contact_city': '',
            'contact_postalCode': '',
            'contact_country': '',
            'contact_email': '',
            'contact_administrativeArea': '', 
            'contact_role': ''
        }
    }
}

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'GeoMetadata_dialog_base.ui'))


class GeoMetadataDialog(QtWidgets.QDialog, FORM_CLASS):
    # ---------------------------- FUNÇÃO INIT ----------------------------
    def __init__(self, parent=None, iface=None):
        """Constructor."""
        super(GeoMetadataDialog, self).__init__(parent)
        self.setupUi(self)

        # 2. Salve o iface para podermos usá-lo em outros métodos
        self.iface = iface

        # --- Preenchimento Inicial do Formulário ---
        self.populate_comboboxes()
        
        # 3. Vamos adicionar a chamada para a nossa nova função aqui
        self.auto_fill_from_layer()

        # --- Conexões de Botões ---
        self.btn_exp_xml.clicked.connect(self.exportar_to_xml)
        self.btn_exp_geo.clicked.connect(self.exportar_to_geo)

        # Conecta a mudança do ComboBox de presets à função de preenchimento
        self.comboBox_contact_presets.currentIndexChanged.connect(self.on_contact_preset_changed)



    # ---------------------------- FUNÇÃO DE CONEXÃO DE BOTÃO ----------------------------
    def exportar_to_xml(self):
        """Coleta dados, gera o XML e pede ao usuário para salvá-lo."""
        
        metadata_dict = self.collect_data()
        
        try:
            plugin_dir = os.path.dirname(__file__)
            template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml') # Verifique o nome do arquivo
            
            # Esta linha agora vai funcionar por causa do import
            xml_content = xml_generator.generate_xml_from_template(metadata_dict, template_path)
            
            safe_title = metadata_dict.get('title', 'metadados').replace(' ', '_')
            suggested_filename = f"{safe_title}.xml"

            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, 
                "Salvar Metadados XML", 
                suggested_filename,
                "Arquivos XML (*.xml)"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(xml_content)
                
                self.iface.messageBar().pushMessage(
                    "Sucesso", 
                    f"Metadados salvos em: {file_path}", 
                    level=Qgis.Success, 
                    duration=5
                )

        except Exception as e:
            print(f"Erro ao gerar ou salvar XML: {e}")
            import traceback
            traceback.print_exc()
            
            # Substitua os '...' pela chamada completa
            self.iface.messageBar().pushMessage(
                "Erro", 
                f"Falha ao gerar XML: {e}", 
                level=Qgis.Critical
            )
            
        # --- PRÓXIMO PASSO (FUTURO) ---
        # 3. Passar metadata_dict para a função que gera o XML.
        # xml_output = seu_script_de_conversao(metadata_dict)
        # print(xml_output)

        # --- Testando a leitura do ComboBox ---
        #status_texto = self.comboBox_status_codeListValue.currentText()
        #status_valor_xml = self.comboBox_status_codeListValue.currentData()
        #print(f"Status (Texto): '{status_texto}'")
        #print(f"Status (Valor para XML): '{status_valor_xml}'")        



    # ---------------------------- FUNÇÃO DE CONEXÃO DE BOTÃO ----------------------------
    def exportar_to_geo(self):
        print("--- EXPORTANDO PARA O GEOHAB ---")
        titulo =  self.lineEdit_title.text()
        print(f"Título:: '{titulo}'")

    # FUNÇÃO PARA POPULAR COMBOBOXEIS
    def populate_comboboxes(self):        
        # --- Preenche o ComboBox de Status ---
        status_options = [
            ('Arquivo Antigo', 'historicalArchive'),
            ('Concluído', 'completed'),
            ('Contínuo', 'onGoing'),
            ('Em Desenvolvimento', 'underDevelopment'),
            ('Necessário', 'required'),
            ('Obsoleto', 'obsolete'),            
            ('Planejado', 'planned')
        ]
        
        self.comboBox_status_codeListValue.clear()  # Limpa o combo antes de adicionar
        for text, data in status_options:
            # Adiciona o texto visível (text) e o dado oculto (data)
            self.comboBox_status_codeListValue.addItem(text, data)

        setorList_options = [             
            ('CDHU', 'cdhu'),
            ('DPDU', 'dpdu'),
            ('SPHU', 'sphu'),
            ('SSARU', 'ssaru'),
            ('TERRAS', 'terras')
        ]
        
        self.comboBox_contact_presets.clear()
        for text, data in setorList_options:
            self.comboBox_contact_presets.addItem(text, data)

        typeEspatial_options = [             
            ('Grid/raster', 'grid'),
            ('Modelo estereofónico', 'stereoscopicModel'),
            ('Rede triangular irregular (TIN)', 'tin'),
            ('Tabela de texto', 'textTable'),              
            ('Vetor', 'vector'),            
            ('Vídeo', 'video')
        ]
        
        self.comboBox_MD_SpatialRepresentationTypeCode.clear()
        for text, data in typeEspatial_options:
            self.comboBox_MD_SpatialRepresentationTypeCode.addItem(text, data) 

        language_options = [             
            ('Português', 'por'),
            ('Inglês', 'eng'),
            ('Espanhol', 'spa'),
            ('Françês', 'fra'),
            ('Alemão', 'ger')
        ]
        
        self.comboBox_LanguageCode.clear()
        for text, data in language_options:
            self.comboBox_LanguageCode.addItem(text, data)

        characterSet_options = [             
            ('UTF-8', 'utf8')
        ]
        
        self.comboBox_characterSet.clear()
        for text, data in characterSet_options:
            self.comboBox_characterSet.addItem(text, data)

        categoric_options = [             
            ('Agricultura, pesca ou pecuária', 'farming'),
            ('Biotipos', 'biota'),
            ('Limites Administrativos', 'boundaries'),
            ('Climatologia, Meteorologia ou atmosfera', 'climatologyMeteorologyAtmosphere'),
            ('Econômia', 'economy'),
            ('Altimetria, Batimetria ou Topografia', 'elevation'),
            ('Informação GeoCientífica', 'geoscientificInformation'),
            ('Saúde', 'health'),
            ('Mapas de base, Coberturas Aéreas, imagens de Satélite', 'imageryBaseMapsEarthCover'),
            ('Informação Militar', 'intelligenceMilitary'),
            ('Águas Interiores', 'inlandWaters'),
            ('Localização', 'location'),
            ('Oceanos', 'oceans'),
            ('Planejamento e Cadastro', 'planningCadastre'),
            ('Sociedade e Cultura', 'society'),
            ('Infraestrutura', 'structure'),
            ('Transportes', 'transportation'),
            ('Infraestruturas de Comunicação', 'utilitiesCommunication')
        ]
        
        self.comboBox_topicCategory.clear()
        for text, data in categoric_options:
            self.comboBox_topicCategory.addItem(text, data)

        hierarchy_options = [             
            ('Atributo', 'attribute'),
            ('Feição', 'feature'),
            ('Conjunto de dados', 'dataset'),
            ('Conjunto de dados não-geográficos', 'nonGeographicDataset'),
            ('Coleção', 'collectionSession'),
            ('Modelo', 'model'),
            ('Serviço', 'service'),
            ('Seção de coleção', 'fieldSession'),
            ('Software', 'software'),
            ('Série', 'series'),
            ('Tile', 'tile'),
            ('Tipo de Atributo', 'attributeType'),
            ('Tipo de Feição', 'featureType'),
            ('Tipo de Propriedade', 'propertyType')
        ]
        
        self.comboBox_hierarchyLevel.clear()
        for text, data in hierarchy_options:
            self.comboBox_hierarchyLevel.addItem(text, data)
    #Extras
        role_options = [             
            ('Autor', 'author'),
            ('Depositário', 'custodian'),
            ('Distribuidor', 'distributor'),
            ('Dono', 'owner'),
            ('Fornecedor de recurso', 'resourceProvider'),
            ('Investigador principal', 'principalInvestigator'),
            ('Organizador', 'processor'),
            ('Originador', 'originator'),
            ('Ponto de contato', 'pointOfContact'),
            ('Publicador', 'publisher'),
            ('Utilizador', 'user')
        ]
        
        self.comboBox_contact_role.clear()
        for text, data in role_options:
            self.comboBox_contact_role.addItem(text, data)

        role_states = [    
            ('São Paulo', 'SP'),         
            ('Acre', 'AC'),
            ('Alagoas', 'AL'),
            ('Amapá', 'AP'),
            ('Amazonas', 'AM'),
            ('Bahia', 'BA'),
            ('Ceará', 'CE'),
            ('Distrito Federal', 'DF'),
            ('Espírito Santo', 'ES'),
            ('Goiás', 'GO'),
            ('Maranhão', 'MA'),
            ('Mato Grosso', 'MT'),
            ('Mato Grosso do Sul', 'MS'),
            ('Minas Gerais', 'MG'),
            ('Pará', 'PA'),
            ('Paraíba', 'PB'),
            ('Paraná', 'PR'),
            ('Pernambuco', 'PE'),
            ('Piauí', 'PI'),
            ('Rio de Janeiro', 'RJ'),
            ('Rio Grande do Norte', 'RN'),
            ('Rio Grande do Sul', 'RS'),
            ('Rondônia', 'RO'),
            ('Roraima', 'RR'),
            ('Santa Catarina', 'SC'),
            ('Sergipe', 'SE'),
            ('Tocantins', 'TO')
        ]
        
        self.comboBox_contact_administrativeArea.clear()
        for text, data in role_states:
            self.comboBox_contact_administrativeArea.addItem(text, data)                  
        
        
    
    # ---------------------------- FUNÇÃO PARA PREENCHER TÍTULO E BBOX ----------------------------
    def auto_fill_from_layer(self):
        """Preenche campos do formulário automaticamente com base na camada ativa."""
        
        # Verificação de segurança: se o iface não foi passado, não faz nada.
        if not self.iface:
            return
            
        # 1. Pega a camada que o usuário selecionou no QGIS
        layer = self.iface.activeLayer()
        
        # 2. VERIFICAÇÃO DE SEGURANÇA: Se nenhuma camada estiver selecionada, para a execução.
        if not layer:
            print("Nenhuma camada ativa para preencher os metadados.")
            # Aqui poderíamos desabilitar os campos de BBOX para o usuário saber o porquê.
            # Por enquanto, apenas retornamos para evitar erros.
            return

        print(f"Preenchendo formulário com dados da camada: '{layer.name()}'")

        # --- PREENCHIMENTO AUTOMÁTICO ---

        # 3. Preenche o TÍTULO com o nome da camada
        self.lineEdit_title.setText(layer.name())
        
        # 4. Preenche a BBOX (Extensão Geográfica)
        extent = layer.extent()
        
        # IMPORTANTE: Verifique os objectNames dos seus campos de BBOX!
        # O código abaixo usa a convenção que discutimos.
        # A formatação ':.6f' garante que o número terá 6 casas decimais.
        self.lineEdit_westBoundLongitude.setText(f"{extent.xMinimum():.6f}")
        self.lineEdit_eastBoundLongitude.setText(f"{extent.xMaximum():.6f}")
        self.lineEdit_southBoundLatitude.setText(f"{extent.yMinimum():.6f}")
        self.lineEdit_northBoundLatitude.setText(f"{extent.yMaximum():.6f}")
    


    # ---------------------------- FUNÇÃO DE COLETA PARA SAÍDA DE DADOS ----------------------------
    def collect_data(self):
        """Lê todos os widgets do formulário e retorna um dicionário com os dados."""
        
        data = {}
        
        # --- Campos de Texto (QLineEdit e QTextEdit) ---
        data['title'] = self.lineEdit_title.text()
        data['edition'] = str(self.spinBox_edition.value())
        data['abstract'] = self.textEdit_abstract.toPlainText()
        keywords_string = self.lineEdit_MD_Keywords.text()
        data['MD_Keywords'] = [k.strip() for k in keywords_string.split(',') if k.strip()]
        data['spatialResolution_denominator'] = self.lineEdit_textEdit_spatialResolution_denominator.text()
        ## EXTRAS
        data['contact_individualName'] = self.lineEdit_contact_individualName.text()
        data['contact_organisationName'] = self.lineEdit_contact_organisationName.text()
        data['contact_positionName'] = self.lineEdit_contact_positionName.text()
        data['contact_phone'] = self.lineEdit_contact_phone.text()
        data['contact_deliveryPoint'] = self.lineEdit_contact_deliveryPoint.text()
        data['contact_city'] = self.lineEdit_contact_city.text()
        data['contact_postalCode'] = self.lineEdit_contact_postalCode.text()
        data['contact_country'] = self.lineEdit_contact_country.text()
        data['contact_email'] = self.lineEdit_contact_email.text()
        
 
        # --- Campos de Data/Hora (QDateTimeEdit) ---
        data['dateStamp'] = self.dateTimeEdit_dateStamp.dateTime().toUTC().toString("yyyy-MM-ddTHH:mm:ss'Z'")
        data['date_creation'] = self.dateTimeEdit_date_creation.dateTime().toString("yyyy-MM-ddTHH:mm:sszzz")
        
        # --- ComboBoxes ---
        data['status_codeListValue'] = self.comboBox_status_codeListValue.currentData()
        data['MD_SpatialRepresentationTypeCode'] = self.comboBox_MD_SpatialRepresentationTypeCode.currentData()
        data['LanguageCode'] = self.comboBox_LanguageCode.currentData()
        data['characterSet'] = self.comboBox_characterSet.currentData()
        data['topicCategory'] = self.comboBox_topicCategory.currentData()
        data['hierarchyLevel'] = self.comboBox_hierarchyLevel.currentData()
        ## EXTRAS
        data['contact_administrativeArea'] = self.comboBox_contact_administrativeArea.currentData()
        data['contact_role'] = self.comboBox_contact_role.currentData()
        
        
        # --- BBOX (lendo dos campos que preenchemos) ---
        data['westBoundLongitude'] = self.lineEdit_westBoundLongitude.text()
        data['eastBoundLongitude'] = self.lineEdit_eastBoundLongitude.text()
        data['southBoundLatitude'] = self.lineEdit_southBoundLatitude.text()
        data['northBoundLatitude'] = self.lineEdit_northBoundLatitude.text()
                
        return data
    


    # ---------------------------- FUNÇÃO PREENCHIMENTO DE CONTATO AUTOMÁTICO ----------------------------
    def set_combobox_by_data(self, combo_box, data_value):
        """Encontra e seleciona um item em um ComboBox pelo userData."""
        for index in range(combo_box.count()):
            if combo_box.itemData(index) == data_value:
                combo_box.setCurrentIndex(index)
                return
    
    def on_contact_preset_changed(self):
        """Preenche os campos de contato com base no preset selecionado."""
        
        # Pega a chave do preset selecionado (ex: 'cdhu')
        preset_key = self.comboBox_contact_presets.currentData()
        
        # Busca os dados no nosso dicionário
        contact_data = CONTATOS_PREDEFINIDOS.get(preset_key)
        
        if not contact_data:
            return # Sai se não encontrar nada

        # Preenche cada QLineEdit com os dados correspondentes
        self.lineEdit_contact_individualName.setText(contact_data.get('contact_individualName', ''))
        self.lineEdit_contact_organisationName.setText(contact_data.get('contact_organisationName', ''))
        self.lineEdit_contact_positionName.setText(contact_data.get('contact_positionName', ''))
        self.lineEdit_contact_phone.setText(contact_data.get('contact_phone', ''))
        self.lineEdit_contact_deliveryPoint.setText(contact_data.get('contact_deliveryPoint', ''))
        self.lineEdit_contact_city.setText(contact_data.get('contact_city', ''))
        self.lineEdit_contact_postalCode.setText(contact_data.get('contact_postalCode', ''))
        self.lineEdit_contact_country.setText(contact_data.get('contact_country', ''))
        self.lineEdit_contact_email.setText(contact_data.get('contact_email', ''))
        self.set_combobox_by_data(self.comboBox_contact_administrativeArea, contact_data.get('contact_administrativeArea', ''))
        self.set_combobox_by_data(self.comboBox_contact_role, contact_data.get('contact_role', ''))




             
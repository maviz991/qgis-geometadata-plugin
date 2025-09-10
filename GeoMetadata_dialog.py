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
from datetime import datetime
from qgis.PyQt.QtCore import Qt
from . import xml_generator
from qgis.core import Qgis
from . import xml_parser
from qgis.PyQt.QtCore import QDateTime
#Seção API GN
import requests
import json
from qgis.core import Qgis
from . import xml_generator
#Integração login
from .login_dialog import LoginDialog

CONTATOS_PREDEFINIDOS = {
        'cdhu': {
            'uuid': 'b98c4847-4d5c-43e1-a5eb-bd0228f6903a',
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
            'uuid': 'a44bfd3a-a9f4-4caf-ba04-6ca36ab44111',
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
            'uuid': '648b9e9f-5b88-4e50-8cce-efa78199515e',
            'contact_individualName': 'SSARU',
            'contact_organisationName': 'Superintendecia Social de Ação em Recuperação Urbana',
            'contact_positionName': '/',
            'contact_phone': '+55 11 2505-2352',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 7º andar',
            'contact_city': 'São Paulo',
            'contact_postalCode': '01014-930',
            'contact_country': 'Brasil',
            'contact_email': 'mapeamento.ssaru@cdhu.sp.gov.br',
            'contact_administrativeArea': 'SP',
            'contact_role': 'processor'
        },
        'terras': {
            'uuid': '14e0f9a4-81a6-430e-9165-8af35481d8ac',
            'contact_individualName': 'TERRAS',
            'contact_organisationName': 'Superintendecia de Terras',
            'contact_positionName': '/',
            'contact_phone': '+55 11 2505-0000',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 6º andar',
            'contact_city': 'São Paulo',
            'contact_postalCode': '01014-930',
            'contact_country': 'Brasil',
            'contact_email': 'terras@cdhu.sp.gov.br',
            'contact_administrativeArea': 'SP',
            'contact_role': 'processor'
        },
        'sphu': {
            'uuid': '14e0f9a4-81a6-430e-9165-8af35481d8ac',
            'contact_individualName': 'SPHU',
            'contact_organisationName': 'Superintendecia de Terras',
            'contact_positionName': '/',
            'contact_phone': '+55 11 2505-0000',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 6º andar',
            'contact_city': 'São Paulo',
            'contact_postalCode': '01014-930',
            'contact_country': 'Brasil',
            'contact_email': 'terras@cdhu.sp.gov.br',
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
        self.btn_salvar.clicked.connect(self.salvar_metadados_sidecar) #SALVAR


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
    #def exportar_to_geo(self):
    #    print("--- EXPORTANDO PARA O GEOHAB ---")
    #    titulo =  self.lineEdit_title.text()
    #    print(f"Título:: '{titulo}'")

    # ---------------------------- FUNÇÃO PARA POPULAR COMBOBOXEIS ----------------------------
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
        """
        Tenta carregar os dados de um arquivo XML 'sidecar'. Se não encontrar,
        preenche os campos Título e BBOX com os dados padrão da camada.
        """
        
        # Primeiro, verifica se temos a interface do QGIS e uma camada ativa.
        if not self.iface:
            return
        layer = self.iface.activeLayer()
        if not layer:
            # Se nenhuma camada estiver ativa, não há nada a fazer.
            return

        # --- NOVA LÓGICA DE CARREGAMENTO ---
        
        # 1. Tenta obter um caminho válido para o arquivo .xml da camada.
        #    Esta função retorna um caminho de arquivo ou None.
        metadata_path = self.get_sidecar_metadata_path()
        
        # 2. Se um caminho válido foi encontrado E o arquivo XML de fato existe...
        if metadata_path and os.path.exists(metadata_path):
            print(f"Arquivo de metadados encontrado: {metadata_path}")
            
            # ...chama nosso parser para ler o XML e transformá-lo em um dicionário.
            data_from_xml = xml_parser.parse_xml_to_dict(metadata_path)
            
            # Se o parser funcionou e retornou dados...
            if data_from_xml:
                # ...preenche o formulário com os dados do XML...
                self.populate_form_from_dict(data_from_xml)
                # ...e PARA a execução aqui. A tarefa está concluída.
                return
        
        # --- LÓGICA PADRÃO (SÓ EXECUTA SE O XML NÃO FOR CARREGADO) ---
        print("Nenhum arquivo XML válido encontrado. Preenchendo com dados padrão da camada.")
        
        # Preenche o TÍTULO com o nome da camada
        self.lineEdit_title.setText(layer.name())
        
        # Preenche a BBOX (Extensão Geográfica)
        extent = layer.extent()
        self.lineEdit_westBoundLongitude.setText(f"{extent.xMinimum():.6f}")
        self.lineEdit_eastBoundLongitude.setText(f"{extent.xMaximum():.6f}")
        self.lineEdit_southBoundLatitude.setText(f"{extent.yMinimum():.6f}")
        self.lineEdit_northBoundLatitude.setText(f"{extent.yMaximum():.6f}")
        


    # ---------------------------- FUNÇÃO DE COLETA PARA SAÍDA DE DADOS ----------------------------
    def collect_data(self):
        """Lê todos os widgets do formulário e retorna um dicionário com os dados."""
        data = {}
            
        # --- LÓGICA DE UUID PARA PRESETS ---
        # 1. Pega a chave do preset que o usuário selecionou (ex: 'ssaru')
        preset_key = self.comboBox_contact_presets.currentData()
        
        # 2. Se um preset válido foi selecionado...
        if preset_key and preset_key != 'nenhum':
            # ...busca os dados completos desse preset no nosso dicionário...
            preset_data = CONTATOS_PREDEFINIDOS.get(preset_key, {})
            # ...e adiciona o UUID fixo dele ao nosso dicionário de dados final.
            data['uuid'] = preset_data.get('uuid')

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
        # Pega o QDateTime do widget
        qdt_creation = self.dateTimeEdit_date_creation.dateTime()
        # Converte para um objeto datetime "ingênuo" do Python
        naive_datetime = qdt_creation.toPyDateTime()
        # Pega o fuso horário local do sistema e torna o datetime "consciente"
        aware_datetime = naive_datetime.astimezone()
        # Formata no padrão ISO 8601 completo, que inclui o fuso
        data['date_creation'] = aware_datetime.isoformat()
        #data['date_creation'] = self.dateTimeEdit_date_creation.dateTime().toString(Qt.ISODate)
        #data['date_creation'] = self.dateTimeEdit_date_creation.dateTime().toString("yyyy-MM-ddTHH:mm:sszzz")
        
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

    #-----------------------------------------------------------------------#
    #------------------------------ Bugfix 1 -------------------------------#
    #-----------------------------------------------------------------------#

    # --------------------------- FUNÇÃO GET PATH ---------------------------
    def get_sidecar_metadata_path(self):
        """
        Obtém o caminho esperado para o arquivo XML sidecar da camada ativa.
        Retorna o caminho ou None se a camada não for baseada em arquivo.
        """
        layer = self.iface.activeLayer()
        if not layer:
            return None

        # layer.source() é geralmente o mais confiável para obter o caminho do arquivo
        source_path = layer.source()
        
        # Lógica para lidar com camadas dentro de ZIPs
        if '|' in source_path:
            source_path = source_path.split('|')[0]
        
        if 'vsizip' in source_path:
            # Extrai o caminho real do .zip de um caminho virtual
            # Ex: /vsizip/C:/caminho/arquivo.zip/camada.shp -> C:/caminho/arquivo.zip
            path_parts = source_path.split('/')
            zip_path_parts = []
            for part in path_parts:
                if '.zip' in part:
                    zip_path_parts.append(part)
                    break
                if part != 'vsizip' and part != '':
                    zip_path_parts.append(part)
            source_path = os.path.join(*zip_path_parts)
            # No Windows, pode precisar de um ajuste para a letra da unidade
            if ':' in zip_path_parts[0]:
                source_path = zip_path_parts[0] + os.sep + os.path.join(*zip_path_parts[1:])
                

        # Verifica se o caminho é realmente um arquivo antes de continuar
        if os.path.isfile(os.path.splitext(source_path)[0] + os.path.splitext(source_path)[1]):
            return source_path + ".xml"
        else:
            print(f"A camada '{layer.name()}' não parece ser baseada em um arquivo local. Não foi possível determinar o caminho para o metadado.")
            return None



    # ---------------------------- FUNÇÃO SALVAR ----------------------------
    def salvar_metadados_sidecar(self):
        """
        Coleta os dados, gera o XML e o salva como um arquivo .xml 'sidecar'
        ao lado do arquivo da camada ativa.
        """
        try:
            # 1. Usa a nova função centralizada para obter o caminho de forma segura.
            #    Toda a lógica de detecção de caminho (ZIP, etc.) está dentro dela.
            metadata_path = self.get_sidecar_metadata_path()
            
            # 2. Se a função retornou None, a camada não é adequada. Mostra um aviso e para.
            if not metadata_path:
                self.iface.messageBar().pushMessage(
                    "Aviso", 
                    "A camada selecionada não é baseada em arquivo ou seu caminho não pôde ser determinado. Metadados não foram salvos.", 
                    level=Qgis.Warning,
                    duration=6
                )
                return # Para a execução da função aqui.
            
            # 3. O resto da lógica para coletar dados, gerar e salvar o XML.
            #    Este bloco continua exatamente o mesmo de antes.
            metadata_dict = self.collect_data()
            plugin_dir = os.path.dirname(__file__)
            template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml')
            xml_content = xml_generator.generate_xml_from_template(metadata_dict, template_path)
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
                
            self.iface.messageBar().pushMessage(
                "Sucesso", 
                f"Metadados salvos em: {metadata_path}", 
                level=Qgis.Success, 
                duration=9
            )

        except Exception as e:
            # Bloco de tratamento de erros, caso algo dê errado.
            print(f"Erro ao salvar arquivo de metadados sidecar: {e}")
            import traceback
            traceback.print_exc()
            self.iface.messageBar().pushMessage(
                "Erro", 
                f"Falha ao salvar metadados: {e}", 
                level=Qgis.Critical
            )

    # ---------------------------- FUNÇÃO CARREGAR XML ----------------------------
    def populate_form_from_dict(self, data_dict):
        """Preenche os widgets do formulário a partir de um dicionário."""
        if not data_dict:
            return

        # --- PREENCHE CAMPOS DE TEXTO ---
        self.lineEdit_title.setText(data_dict.get('title', ''))
        edition_str = data_dict.get('edition', '1') 
        try:
            # Tenta converter a string para um inteiro
            edition_int = int(edition_str) 
            # Define o valor do SpinBox
            self.spinBox_edition.setValue(edition_int) 
        except (ValueError, TypeError):
            # Se a conversão falhar, define um valor padrão seguro (ex: 1)
            self.spinBox_edition.setValue(1)
        self.textEdit_abstract.setText(data_dict.get('abstract', ''))
        self.lineEdit_MD_Keywords.setText(data_dict.get('MD_Keywords', ''))
        self.lineEdit_textEdit_spatialResolution_denominator.setText(data_dict.get('spatialResolution_denominator', ''))
        self.lineEdit_contact_individualName.setText(data_dict.get('contact_individualName', ''))
        self.lineEdit_contact_organisationName.setText(data_dict.get('contact_organisationName', ''))
        self.lineEdit_contact_positionName.setText(data_dict.get('contact_positionName', ''))
        self.lineEdit_contact_phone.setText(data_dict.get('contact_phone', ''))
        self.lineEdit_contact_deliveryPoint.setText(data_dict.get('contact_deliveryPoint', ''))
        self.lineEdit_contact_city.setText(data_dict.get('contact_city', ''))
        self.lineEdit_contact_postalCode.setText(data_dict.get('contact_postalCode', ''))
        self.lineEdit_contact_country.setText(data_dict.get('contact_country', ''))
        self.lineEdit_contact_email.setText(data_dict.get('contact_email', ''))
      

        # --- PREENCHE COMBOBOXES ---
        self.set_combobox_by_data(self.comboBox_status_codeListValue, data_dict.get('status_codeListValue'))
        self.set_combobox_by_data(self.comboBox_MD_SpatialRepresentationTypeCode, data_dict.get('MD_SpatialRepresentationTypeCode'))
        self.set_combobox_by_data(self.comboBox_LanguageCode, data_dict.get('LanguageCode'))
        self.set_combobox_by_data(self.comboBox_characterSet, data_dict.get('characterSet'))
        self.set_combobox_by_data(self.comboBox_topicCategory, data_dict.get('topicCategory'))
        self.set_combobox_by_data(self.comboBox_hierarchyLevel, data_dict.get('hierarchyLevel'))
        self.set_combobox_by_data(self.comboBox_contact_administrativeArea, data_dict.get('contact_administrativeArea'))
        self.set_combobox_by_data(self.comboBox_contact_role, data_dict.get('contact_role'))

        # --- PREENCHE BBOX ---
        self.lineEdit_westBoundLongitude.setText(data_dict.get('westBoundLongitude', ''))
        self.lineEdit_eastBoundLongitude.setText(data_dict.get('eastBoundLongitude', ''))
        self.lineEdit_southBoundLatitude.setText(data_dict.get('southBoundLatitude', ''))
        self.lineEdit_northBoundLatitude.setText(data_dict.get('northBoundLatitude', ''))

        # --- PREENCHE DATAS (requer conversão de string para QDateTime) ---
        date_creation_str = data_dict.get('date_creation')
        if date_creation_str:
            # Precisamos importar QDateTime from PyQt5.QtCore
            self.dateTimeEdit_date_creation.setDateTime(QDateTime.fromString(date_creation_str, Qt.ISODate))
            
        print("Formulário preenchido com dados de um arquivo XML existente.")
        

    # ---------------------------- FUNÇÃO CARREGAR PARA O GEOHAB --------------------------- tamplate_mgb20
    def exportar_to_geo(self):
        """
        Abre uma janela de login, obtém as credenciais e então executa o fluxo
        de autenticação e envio de metadados.
        """
        try:
            # --- ETAPA DE LOGIN DO USUÁRIO ---
            from .login_dialog import LoginDialog
            login_dialog = LoginDialog(self)
            
            # Mostra o diálogo e espera o usuário clicar em "Login" ou "Cancel"
            if login_dialog.exec_() == QtWidgets.QDialog.Accepted:
                # Pega as credenciais que o usuário digitou
                USER, PASSWORD = login_dialog.getCredentials()
                
                # Validação
                if not USER or not PASSWORD:
                    self.iface.messageBar().pushMessage("Aviso", "Usuário e senha são obrigatórios.", level=Qgis.Warning)
                    return

                # --- A LÓGICA DE EXPORTAÇÃO COMEÇA AQUI ---
                
                # --- ETAPA 1: PREPARAÇÃO ---
                print("Coletando dados e gerando XML...")
                metadata_dict = self.collect_data()
                plugin_dir = os.path.dirname(__file__)
                template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml')
                xml_payload = xml_generator.generate_xml_from_template(metadata_dict, template_path)
                
                # --- ETAPA 2: CONFIGURAÇÃO ---
                LOGIN_URL = "https://geo.cdhu.sp.gov.br/login"
                GEONETWORK_CATALOG_URL = "https://geo.cdhu.sp.gov.br/geonetwork/srv/eng/catalog.search"
                RECORDS_URL = "https://geo.cdhu.sp.gov.br/geonetwork/srv/api/records"
                ORIGIN_URL = "https://geo.cdhu.sp.gov.br"
                
                self.iface.messageBar().pushMessage("Info", f"Autenticando como {USER}...", level=Qgis.Info)

                # --- ETAPA 3: LOGIN SIMULADO ---
                with requests.Session() as session:
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
                    })
                    session.get(LOGIN_URL, verify=False)

                    # Usa as credenciais obtidas da janela de login
                    login_data = {'username': USER, 'password': PASSWORD}
                    login_headers = {'Referer': LOGIN_URL, 'Origin': ORIGIN_URL}
                    
                    print(f"Enviando POST de login para: {LOGIN_URL}")
                    login_response = session.post(LOGIN_URL, data=login_data, headers=login_headers, verify=False)

                    # Verificação de autenticação robusta (corrigida)
                    print(f"Status da resposta de login: {login_response.status_code}")
                    print(f"URL final após login: {login_response.url}")
                    print(f"Cookies da sessão: {list(session.cookies.keys())}")
                    
                    # Verifica se a autenticação foi bem-sucedida
                    auth_success = False
                    
                    # Método 1: Verifica cookies de sessão
                    session_cookies = ['SESSION', 'JSESSIONID', 'session', 'auth']
                    for cookie_name in session_cookies:
                        if cookie_name in session.cookies:
                            auth_success = True
                            print(f"Autenticação detectada: cookie '{cookie_name}' encontrado.")
                            break
                    
                    # Método 2: Verifica se há redirecionamento ou se a URL mudou
                    if login_response.status_code in [200, 302] and login_response.url != LOGIN_URL:
                        auth_success = True
                        print("Autenticação detectada: redirecionamento para URL diferente.")
                    
                    # Método 3: Para status 200, verifica se não há indicadores de erro
                    if not auth_success and login_response.status_code == 200:
                        error_indicators = ['error', 'invalid', 'incorrect', 'failed', 'login', 'senha', 'usuario']
                        response_text = login_response.text.lower()
                        has_error = any(indicator in response_text for indicator in error_indicators)
                        
                        if not has_error:
                            auth_success = True
                            print("Autenticação detectada: status 200 sem indicadores de erro.")
                    
                    if not auth_success:
                        # Salva a resposta para debug
                        debug_file = os.path.join(plugin_dir, 'login_response_debug.html')
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(login_response.text)
                        print(f"Resposta de login salva em: {debug_file}")
                        
                        raise Exception(f"Falha na autenticação: Status {login_response.status_code}. Verifique suas credenciais.")
                    
                    print("Autenticação bem-sucedida.")

                    # --- ETAPA 4: ENVIAR PARA O GEONETWORK ---
                    print(f"Acessando catálogo: {GEONETWORK_CATALOG_URL}")
                    catalog_response = session.get(GEONETWORK_CATALOG_URL, verify=False)
                    print(f"Status do acesso ao catálogo: {catalog_response.status_code}")
                    
                    # Busca o token CSRF de forma mais robusta
                    csrf_token = None
                    for cookie in session.cookies:
                        if cookie.name == 'XSRF-TOKEN':
                            csrf_token = cookie.value
                            print(f"Token CSRF encontrado: {csrf_token[:20]}...")
                            break
                    
                    # Se não encontrou o token no caminho específico, tenta buscar genericamente
                    if not csrf_token:
                        csrf_token = session.cookies.get('XSRF-TOKEN')
                        if csrf_token:
                            print(f"Token CSRF encontrado (genérico): {csrf_token[:20]}...")
                    
                    if not csrf_token:
                        print("Aviso: Cookie XSRF-TOKEN não encontrado. Tentando prosseguir sem ele.")
                    
                    gn_headers = {
                        'Accept': 'application/json',
                        'Referer': GEONETWORK_CATALOG_URL
                    }
                    
                    # Adiciona o token CSRF apenas se encontrado
                    if csrf_token:
                        gn_headers['X-XSRF-TOKEN'] = csrf_token
                    
                    params = {'publishToAll': 'true'}
                    files_payload = {'file': ('metadata.xml', xml_payload.encode('utf-8'), 'application/xml')}
                    
                    print("Enviando metadados para o GeoNetwork...")
                    gn_response = session.post(
                        RECORDS_URL, params=params, files=files_payload, headers=gn_headers, verify=False
                    )

                    # --- ETAPA 5: TRATAR A RESPOSTA FINAL ---
                    print(f"Status do envio de metadados: {gn_response.status_code}")
                    print(f"Resposta do servidor: {gn_response.text[:200]}...")
                    
                    if gn_response.status_code == 201:
                        try:
                            response_data = gn_response.json()
                            uuid_criado = response_data.get('uuid', 'N/A')
                            self.iface.messageBar().pushMessage("SUCESSO!", f"Metadados publicados! UUID: {uuid_criado}", level=Qgis.Success, duration=15)
                        except:
                            self.iface.messageBar().pushMessage("SUCESSO!", "Metadados publicados com sucesso!", level=Qgis.Success, duration=15)
                    else:
                        print(f"ERRO do GeoNetwork: {gn_response.status_code} - {gn_response.text}")
                        self.iface.messageBar().pushMessage("Erro", f"Falha no envio (Status: {gn_response.status_code}). Veja o log do console.", level=Qgis.Critical, duration=10)
            
            else:
                # O usuário clicou em "Cancel"
                self.iface.messageBar().pushMessage("Info", "Exportação cancelada pelo usuário.", level=Qgis.Info)
                return

        except requests.exceptions.RequestException as e:
            print(f"ERRO DE REDE: {e}")
            self.iface.messageBar().pushMessage("Erro de Rede", f"Não foi possível conectar: {e}", level=Qgis.Critical)

        except Exception as e:
            print(f"ERRO INESPERADO: {e}")
            import traceback
            traceback.print_exc()
            self.iface.messageBar().pushMessage("Erro Inesperado", f"Ocorreu um erro no plugin: {e}", level=Qgis.Critical)


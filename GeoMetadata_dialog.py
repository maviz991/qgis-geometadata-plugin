# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GeoMetadataDialog | CDHU
                                 A QGIS plugin
 Description
                             -------------------
        copyright            : (C) 2025 by Matheus Aviz | CDHU
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

# --- 1. Imports da Biblioteca Padrão Python ---
import os
import json
from datetime import datetime
import traceback
# --- 2. Imports de Bibliotecas de Terceiros ---
import requests
from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtCore import Qt, QDateTime
from qgis.core import Qgis
# --- 3. Imports de Módulos Locais do Plugin ---
from . import xml_generator
from . import xml_parser
from .geoserver_login_dialog import GeoServerLoginDialog #0210
from .layer_selection_dialog import LayerSelectionDialog #0210
from .plugin_config import config_loader #0210
from .login_dialog import LoginDialog
import pathlib
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject
)

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
            'contact_phone': '+55 11 2505-2553',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 8º andar - Bloco 2',
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
            'contact_organisationName': 'Superintendência Social de Ação em Recuperação Urbana',
            'contact_positionName': '/',
            'contact_phone': '+55 11 2505-2352',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 7º andar',
            'contact_city': 'São Paulo',
            'contact_postalCode': '01014-930',
            'contact_country': 'Brasil',
            'contact_email': 'mapeamento.ssaru@cdhu.sp.gov.br',
            'contact_administrativeArea': 'SP',
            'contact_role': 'author'
        },
        'terras': {
            'uuid': '14e0f9a4-81a6-430e-9165-8af35481d8ac',
            'contact_individualName': 'TERRAS',
            'contact_organisationName': 'Superintendência de Terras',
            'contact_positionName': '/',
            'contact_phone': '+55 11 2505-0000',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 6º andar - Bloco 5',
            'contact_city': 'São Paulo',
            'contact_postalCode': '01014-930',
            'contact_country': 'Brasil',
            'contact_email': 'terras@cdhu.sp.gov.br',
            'contact_administrativeArea': 'SP',
            'contact_role': 'author'
        },
        'sphu': {
            'uuid': '7d1bd2ec-ceee-4f35-a10c-4c37c37355fe',
            'contact_individualName': 'SPHU',
            'contact_organisationName': 'Superintendência de Projetos Habitacionais e Urbanos',
            'contact_positionName': '/',
            'contact_phone': '+55 11 2505-0000',
            'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé',
            'contact_city': 'São Paulo',
            'contact_postalCode': '01014-930',
            'contact_country': 'Brasil',
            'contact_email': 'sphu@cdhu.sp.gov.br',
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
    # -------------------------------------------- FUNÇÃO INIT ------------------------------------------ #
    def __init__(self, parent=None, iface=None):
        self.distribution_data = {} # Armazena os dados finais #02/10
        """Constructor."""
        super(GeoMetadataDialog, self).__init__(parent)
        self.setupUi(self)

        # Usado em outros métodos de action
        self.iface = iface
        # Preenchimento dos Formulários
        self.populate_comboboxes()
        # Preenchimento de dados via xml salvo anteriormente
        self.auto_fill_from_layer()
        # Conexões de Botões
        self.btn_exp_xml.clicked.connect(self.exportar_to_xml)
        self.btn_exp_geo.clicked.connect(self.exportar_to_geo)
        self.btn_salvar.clicked.connect(self.salvar_metadados_sidecar)
        # Conecta a mudança do ComboBox de presets à função de preenchimento
        self.comboBox_contact_presets.currentIndexChanged.connect(self.on_contact_preset_changed)
        self.btn_distribution_info.clicked.connect(self.open_distribution_workflow) #02/10
        # Armazena os dados finais (inicializado como atributo de classe)

    # ------------------------------------- FUNÇÃO EXPORTAR XML ---------------------------------- #
    def exportar_to_xml(self):
        """Coleta dados, gera o XML e pede ao usuário para salvá-lo."""
        
        try:
            metadata_dict = self.collect_data()
            
            plugin_dir = os.path.dirname(__file__)
            template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml')
            
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
                
                # --- MUDANÇA: Feedback Duplo (Pop-up + Barra do QGIS) ---
                metadata_uri = pathlib.Path(file_path).as_uri()
                success_text = (f"Pronto!<br><br>"
                            f"Metadados salvos com sucesso em:.<br>"
                            f'<a href="{metadata_uri}">{file_path}</a>')
                self.show_message("Exportação Concluída", success_text)
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
            
            # --- MUDANÇA: Feedback Duplo (Pop-up + Barra do QGIS) ---
            error_text = f"Ocorreu um erro ao gerar ou salvar o arquivo XML:<br><br>{e}"
            self.show_message("Erro na Exportação", error_text, icon=QtWidgets.QMessageBox.Critical)
            self.iface.messageBar().pushMessage(
                "Erro", 
                f"Falha ao gerar XML: {e}", 
                level=Qgis.Critical
            )

    # ----------------------------------- FUNÇÃO PARA POPULAR COMBOBOXEIS ------------------------------- #
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
            ('Grid|Raster', 'grid'),
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
            ('🇧🇷 Português', 'por'),
            ('🇺🇸 Inglês', 'eng'),
            ('🇪🇸 Espanhol', 'spa'),
            ('🇫🇷 Françês', 'fra'),
            ('🇩🇪 Alemão', 'ger')
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
            ('Mapas, Coberturas Aéreas, imagens de Satélite', 'imageryBaseMapsEarthCover'),
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
            #('Atributo', 'attribute'),
            #('Feição', 'feature'),
            ('Conjunto de dados', 'dataset'),
            #('Conjunto de dados não-geográficos', 'nonGeographicDataset'),
            #('Coleção', 'collectionSession'),
            #('Modelo', 'model'),
            #('Serviço', 'service'),
            #('Seção de coleção', 'fieldSession'),
            #('Software', 'software'),
            #('Série', 'series'),
            #('Tile', 'tile'),
            #('Tipo de Atributo', 'attributeType'),
            #('Tipo de Feição', 'featureType'),
            #('Tipo de Propriedade', 'propertyType')
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

    
    # -------------------------------- FUNÇÃO PARA PREENCHER TÍTULO E BBOX ------------------------------ #
    def auto_fill_from_layer(self):
        """
        Tenta carregar os dados de um arquivo XML 'sidecar'. Se não encontrar,
        preenche os campos Título e BBOX com os dados padrão da camada.
        """
        
        # Verifica camada ativa no QGIS.
        if not self.iface:
            return
        layer = self.iface.activeLayer()
        if not layer:
            return

        # --- LÓGICA DE CARREGAMENTO ---
        # 1. Tenta carregar o preset do layer properties
        preset_key = layer.customProperty('contact_preset_key')
        if preset_key:
            self.set_combobox_by_data(self.comboBox_contact_presets, preset_key)
        
        # 2. Se caminho válido para o arquivo .xml da camada.
        metadata_path = self.get_sidecar_metadata_path()
        
        # 3. Se um caminho válido foi encontrado e verifica se o arquivo XML de fato existe
        if metadata_path and os.path.exists(metadata_path):
            print(f"Arquivo de metadados encontrado: {metadata_path}")
            
            data_from_xml = xml_parser.parse_xml_to_dict(metadata_path) # Chama xml_parser.py para ler o XML e transformá-lo em um dicionário.
            
            
            if data_from_xml: # Always load from XML if data is available
                self.populate_form_from_dict(data_from_xml) # preenche o formulário com os dados do XML
                return
        # --- LÓGICA PADRÃO (SÓ EXECUTA SE O XML NÃO FOR CARREGADO) ---
        print("Nenhum arquivo XML associado a essa camada! Preenchendo com dados padrão da camada.")
        
        # Preenche o TÍTULO com o nome da camada
        self.lineEdit_title.setText(layer.name())
        
        # 1. Pega a extensão e o CRS originais da camada
        original_extent = layer.extent()
        source_crs = layer.crs()
        
        # 2. Define o nosso CRS de destino: Geográficas WGS 84 (Padrão GeoNetwork)
        target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        
        geographic_extent = original_extent

        # 3. Verifica se a reprojeção é realmente necessária
        if source_crs != target_crs:
            print(f"Reprojetando a extensão de {source_crs.authid()} para {target_crs.authid()}")
            # Cria o objeto de transformação
            transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
            # Executa a transformação na extensão
            geographic_extent = transform.transform(original_extent)

        # 4. Preenche os campos do formulário com a extensão em geográficas
        self.lineEdit_westBoundLongitude.setText(f"{geographic_extent.xMinimum():.6f}")
        self.lineEdit_eastBoundLongitude.setText(f"{geographic_extent.xMaximum():.6f}")
        self.lineEdit_southBoundLatitude.setText(f"{geographic_extent.yMinimum():.6f}")
        self.lineEdit_northBoundLatitude.setText(f"{geographic_extent.yMaximum():.6f}")


    # ------------------------------- FUNÇÃO DE COLETA PARA SAÍDA DE DADOS ------------------------------ #
    def collect_data(self):
        """Lê todos os widgets do formulário e retorna um dicionário com os dados."""
        data = {}
            
        # --- LÓGICA DE UUID PARA PRESETS (Setores) ---
        # 1. Pega a chave do preset que o usuário selecionou (ex: 'ssaru')
        preset_key = self.comboBox_contact_presets.currentData()
        
        # 2. Se um preset válido foi selecionado
        if preset_key and preset_key != 'nenhum':
            preset_data = CONTATOS_PREDEFINIDOS.get(preset_key, {}) # busca os dados completos desse preset no dicionário
            data['uuid'] = preset_data.get('uuid') # e adiciona o UUID fixo dele ao dicionário de dados final.

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
        naive_datetime = qdt_creation.toPyDateTime()                # Converte para um objeto datetime
        aware_datetime = naive_datetime.astimezone()                # Pega o fuso horário local do sistema
        data['date_creation'] = aware_datetime.isoformat()          # Formata no padrão ISO 8601 completo, que inclui o fuso
        
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
        
        # --- BBOX ---
        data['westBoundLongitude'] = self.lineEdit_westBoundLongitude.text()
        data['eastBoundLongitude'] = self.lineEdit_eastBoundLongitude.text()
        data['southBoundLatitude'] = self.lineEdit_southBoundLatitude.text()
        data['northBoundLatitude'] = self.lineEdit_northBoundLatitude.text()

        #Combobox Preset selecionada (persistênte)
        preset_key = self.comboBox_contact_presets.currentData()
        layer = self.iface.activeLayer()
        if layer:
            layer.setCustomProperty('contact_preset_key', preset_key)

        #Dados das camadas no dialog dela
        data.update(self.distribution_data)
        data['thumbnail_url'] = self.lineEdit_thumbnail_url.text()
                 
        return data
    

    # --------------------------- FUNÇÃO PREENCHIMENTO DE CONTATO AUTOMÁTICO ---------------------------- #
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
        
        # Busca os dados no dicionário
        contact_data = CONTATOS_PREDEFINIDOS.get(preset_key)
        
        if not contact_data:
            return

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

    #----------------------------------------------------------------------------------------------------#
    #                                                Bugfix 1                                            #
    #----------------------------------------------------------------------------------------------------#


    # ---------------------------------------- FUNÇÃO GET PATH ----------------------------------------- #
    def get_sidecar_metadata_path(self):
        """
        Obtém o caminho esperado para o arquivo XML sidecar, usando layer.source()
        para compatibilidade com GPKG e SHP, com lógica aprimorada para ZIP.
        """
        layer = self.iface.activeLayer()
        if not layer:
            return None

        # Usar layer.source(), que se mostrou compatível com arquivos GPKG.
        source_path = layer.source()

        # --- LÓGICA DE MANIPULAÇÃO DE CAMINHO ---
        # Para fontes como GPKG, o caminho é 'C:/.../dados.gpkg|layername=minha_camada'.
        # A linha abaixo extrai apenas 'C:/.../dados.gpkg'.
        # A verificação de '|' garante que isso não afete caminhos de shapefile.
        if '|' in source_path:
            base_path = source_path.split('|')[0]
        else:
            base_path = source_path
            
        # --- LÓGICA ESPECÍFICA E CORRETA PARA ZIP ---
        # Se o caminho original (não o base_path) vier de um ZIP virtual...
        if 'vsizip' in source_path.lower():
            # ...então precisamos encontrar o caminho real para o arquivo .zip.
            # Ex: /vsizip/C:/caminho/arquivo.zip/camada.shp -> C:/caminho/arquivo.zip
            
            # Remove o prefixo /vsizip/
            path_sem_vsizip = source_path.replace('/vsizip/', '')
            
            # Encontra a posição do .zip e corta a string ali.
            zip_index = path_sem_vsizip.lower().find('.zip')
            if zip_index != -1:
                base_path = path_sem_vsizip[:zip_index + 4]

        # A verificação final deve ser feita no base_path limpo
        if os.path.isfile(base_path):
            return base_path + ".xml"
        else:
            print(f"O caminho da fonte '{base_path}' para a camada '{layer.name()}' não é um arquivo válido.")
            return None
    


    # ------------------------------- FUNÇÃO SALVAR | 'Continuar depois' ------------------------------- #
    def salvar_metadados_sidecar(self):
        """
        Coleta os dados, gera o XML e o salva como um arquivo .xml 'sidecar'
        ao lado do arquivo da camada ativa.
        """
        layer = self.iface.activeLayer()
        if not layer:
            return None
        try:
            # 1. Usa a função get_sidecar_metadata_path para obter o path.
            metadata_path = self.get_sidecar_metadata_path()
            
            # 2. Se a função retornou None, a camada não é adequada. Mostra um aviso e para.
            if not metadata_path:
                warning_text = (f"A camada '{layer.name()}' não está salva no seu computador!<br><br>"
                                f"A função 'Continuar depois' não pode salvar um metadado para você preencher mais tarde.<br><br>"
                                f"SOLUÇÕES:<br>   • Use 'Exportar para XML' para salvar o metadado, mas desvinculado a camada atual.<br>    • Ou salve a camada '{layer.name()}' no seu computador.")
                # Feedback Duplo (Pop-up + Barra do QGIS)
                self.show_message("Não é possível salvar para 'Continuar depois'", warning_text, icon=QtWidgets.QMessageBox.Warning)
                self.iface.messageBar().pushMessage(
                    "Aviso", 
                    "Não é possível usar 'Salvar'. A camada não está salva no seu computador.", 
                    level=Qgis.Warning,
                    duration=10
                )
                return
            
            # 3. Lógica para coletar dados, gerar e salvar o XML.
            metadata_dict = self.collect_data()
            plugin_dir = os.path.dirname(__file__)
            template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml')
            xml_content = xml_generator.generate_xml_from_template(metadata_dict, template_path)

            metadata_uri = pathlib.Path(metadata_path).as_uri()

            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            # --- MUDANÇA: Feedback Duplo (Pop-up + Barra do QGIS) ---
            success_text = (f"Pronto!<br><br>"
                            f"Metadados associados à camada '<b>{layer.name()}</b>'.<br>"
                            f"O arquivo foi salvo no mesmo local da camada:<br>"
                            f'<a href="{metadata_uri}">{metadata_path}</a>')
            self.show_message("Metadados associado a camada corretamente!", success_text)
            self.iface.messageBar().pushMessage(
                "Sucesso", 
                f"Pronto! Metadados associado a camada ativa<br>Metadados salvos em: {metadata_path}", 
                level=Qgis.Success, 
                duration=9
            )

        except Exception as e:
            print(f"Erro ao salvar arquivo de metadados sidecar: {e}")
            import traceback
            traceback.print_exc()
            
            # --- MUDANÇA: Feedback Duplo (Pop-up + Barra do QGIS) ---
            error_text = f"Ocorreu um erro ao tentar salvar o arquivo de metadados:<br><br>{e}"
            self.show_message("Erro ao Salvar", error_text, icon=QtWidgets.QMessageBox.Critical)
            self.iface.messageBar().pushMessage(
                "Erro", 
                f"Falha ao salvar metadados: {e}", 
                level=Qgis.Critical
            )

    def update_distribution_button(self):
        """Atualiza o texto do botão de distribuição com as informações de WMS e WFS."""
        wms_info = self.distribution_data.get('wms_data', {}).get('geoserver_layer_title')
        wfs_info = self.distribution_data.get('wfs_data', {}).get('geoserver_layer_title')

        display_text = []
        if wms_info:
            display_text.append(f"WMS: {wms_info}")
        if wfs_info:
            display_text.append(f"WFS: {wfs_info}")

        if display_text:
            self.btn_distribution_info.setText(f"🔗 Associado a: {', '.join(display_text)}")
        else:
            self.btn_distribution_info.setText("⚠️ Nenhuma camada associada")
        self.btn_distribution_info.update()
    # --------------------------------------- FUNÇÃO CARREGAR XML -------------------------------------- #
    def populate_form_from_dict(self, data_dict):
        """
        Preenche os widgets do formulário a partir de um dicionário, armazena os dados
        de distribuição e deduz o preset de contato.
        """
        if not data_dict:
            return

        # --- ETAPA 1: PREENCHE OS CAMPOS DO FORMULÁRIO PRINCIPAL ---
        self.lineEdit_title.setText(data_dict.get('title', ''))
        edition_str = data_dict.get('edition', '1')
        try:
            self.spinBox_edition.setValue(int(edition_str) if edition_str else 1)
        except (ValueError, TypeError):
            self.spinBox_edition.setValue(1)

        self.textEdit_abstract.setText(data_dict.get('abstract', ''))
        self.lineEdit_MD_Keywords.setText(data_dict.get('MD_Keywords', ''))
        self.lineEdit_textEdit_spatialResolution_denominator.setText(data_dict.get('spatialResolution_denominator', ''))
        
        # Preenche os campos de contato
        self.lineEdit_contact_individualName.setText(data_dict.get('contact_individualName', ''))
        self.lineEdit_contact_organisationName.setText(data_dict.get('contact_organisationName', ''))
        self.lineEdit_contact_positionName.setText(data_dict.get('contact_positionName', ''))
        self.lineEdit_contact_phone.setText(data_dict.get('contact_phone', ''))
        self.lineEdit_contact_deliveryPoint.setText(data_dict.get('contact_deliveryPoint', ''))
        self.lineEdit_contact_city.setText(data_dict.get('contact_city', ''))
        self.lineEdit_contact_postalCode.setText(data_dict.get('contact_postalCode', ''))
        self.lineEdit_contact_country.setText(data_dict.get('contact_country', ''))
        self.lineEdit_contact_email.setText(data_dict.get('contact_email', ''))

        # Preenche ComboBoxes
        self.set_combobox_by_data(self.comboBox_status_codeListValue, data_dict.get('status_codeListValue'))
        self.set_combobox_by_data(self.comboBox_MD_SpatialRepresentationTypeCode, data_dict.get('MD_SpatialRepresentationTypeCode'))
        self.set_combobox_by_data(self.comboBox_LanguageCode, data_dict.get('LanguageCode'))
        self.set_combobox_by_data(self.comboBox_characterSet, data_dict.get('characterSet'))
        self.set_combobox_by_data(self.comboBox_topicCategory, data_dict.get('topicCategory'))
        self.set_combobox_by_data(self.comboBox_hierarchyLevel, data_dict.get('hierarchyLevel'))
        self.set_combobox_by_data(self.comboBox_contact_administrativeArea, data_dict.get('contact_administrativeArea'))
        self.set_combobox_by_data(self.comboBox_contact_role, data_dict.get('contact_role'))

        # Preenche BBOX
        self.lineEdit_westBoundLongitude.setText(data_dict.get('westBoundLongitude', ''))
        self.lineEdit_eastBoundLongitude.setText(data_dict.get('eastBoundLongitude', ''))
        self.lineEdit_southBoundLatitude.setText(data_dict.get('southBoundLatitude', ''))
        self.lineEdit_northBoundLatitude.setText(data_dict.get('northBoundLatitude', ''))

        # Preenche Datas
        date_creation_str = data_dict.get('date_creation')
        if date_creation_str:
            try:
                dt = QDateTime.fromString(date_creation_str, Qt.ISODateWithMs)
                if not dt.isValid():
                    dt = QDateTime.fromString(date_creation_str, Qt.ISODate)
                self.dateTimeEdit_date_creation.setDateTime(dt)
            except Exception as e:
                print(f"Erro ao converter data: {e}")

        # --- ETAPA 2: RESTAURAR DADOS DE DISTRIBUIÇÃO ---
        self.distribution_data['wms_data'] = data_dict.get('wms_data', {})
        self.distribution_data['wfs_data'] = data_dict.get('wfs_data', {})
        self.lineEdit_thumbnail_url.setText(data_dict.get('thumbnail_url', ''))
        
        wms_info = self.distribution_data.get('wms_data', {}).get('geoserver_layer_title')
        wfs_info = self.distribution_data.get('wfs_data', {}).get('geoserver_layer_title')

        display_text = []
        if wms_info:
            display_text.append(f"WMS: {wms_info}")
        if wfs_info:
            display_text.append(f"WFS: {wfs_info}")

        if display_text:
            self.btn_distribution_info.setText(f"🔗 Associado a: {', '.join(display_text)}")
        else:
            self.btn_distribution_info.setText("⚠️ Nenhuma camada associada")
    def update_distribution_button(self):
        """Atualiza o texto do botão de distribuição com as informações de WMS e WFS."""
        wms_info = self.distribution_data.get('wms_data', {}).get('geoserver_layer_title')
        wfs_info = self.distribution_data.get('wfs_data', {}).get('geoserver_layer_title')

        display_text = []
        if wms_info:
            display_text.append(f"WMS: {wms_info}")
        if wfs_info:
            display_text.append(f"WFS: {wfs_info}")

        if display_text:
            self.btn_distribution_info.setText(f"🔗 Associado a: {', '.join(display_text)}")
        else:
            self.btn_distribution_info.setText("⚠️ Nenhuma camada associada")

        # --- ETAPA 3: RESTAURAR O PRESET DE CONTATO ---
        preset_key = data_dict.get('contact_preset_key')
        if preset_key:
            self.set_combobox_by_data(self.comboBox_contact_presets, preset_key)
        else:
            nenhum_index = self.comboBox_contact_presets.findData('nenhum')
            if nenhum_index >= 0:
                self.comboBox_contact_presets.setCurrentIndex(nenhum_index)
                
        print("Formulário preenchido com dados de um Metadado existente.")



    # --------------------------------- FUNÇÃO MSG ALERTAS ---------------------------------- #
    def show_message(self, title, text, icon=QtWidgets.QMessageBox.Information):
        """
        Exibe uma janela de diálogo (MessageBox) padronizada para o usuário.

        :param title: O título da janela.
        :param text: O texto principal da mensagem.
        :param icon: O ícone a ser exibido (Information, Warning, Critical).
        """
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(icon)
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(text)
        msg_box.setWindowTitle(title)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg_box.exec_()
        

    # --------------------------------- FUNÇÃO CARREGAR PARA O GEOHAB ---------------------------------- #
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
                USER, PASSWORD = login_dialog.getCredentials() # Pega as credenciais que o usuário digitou
                
                # Validação
                if not USER or not PASSWORD:
                    # MUDANÇA: Usa MessageBox
                    self.show_message("Aviso", "Usuário e senha são obrigatórios.", icon=QtWidgets.QMessageBox.Warning)
                    return

                # LÓGICA DE EXPORTAÇÃO
                # --- ETAPA 1: PREPARAÇÃO ---
                print("Coletando dados e gerando XML...")
                metadata_dict = self.collect_data()
                plugin_dir = os.path.dirname(__file__)
                template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml')
                xml_payload = xml_generator.generate_xml_from_template(metadata_dict, template_path)
                
                # --- ETAPA 2: CONFIGURAÇÃO ---
                #LOGIN_URL = "https://geohab.cdhu.sp.gov.br/login"
                #GEONETWORK_CATALOG_URL = "https://geohab.cdhu.sp.gov.br/geonetwork/srv/eng/catalog.search"
                #RECORDS_URL = "https://geohab.cdhu.sp.gov.br/geonetwork/srv/api/records"
                #ORIGIN_URL = "https://geohab.cdhu.sp.gov.br"
                gn_urls = config_loader.get_geonetwork_url()
                RECORDS_URL = gn_urls['records_url']
                GEONETWORK_CATALOG_URL = gn_urls['catalog_url']
                # O login e a origem geralmente são a base do domínio
                base_domain = RECORDS_URL.split('/geonetwork')[0]
                LOGIN_URL = f"{base_domain}/login"
                ORIGIN_URL = base_domain
                
                # Mensagem de progresso na barra
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
                    
                    login_response = session.post(LOGIN_URL, data=login_data, headers=login_headers, verify=False) # verify: SSL cetificado atual da Goehab|CDHU estar dando falha

                    # Verificação de autenticação
                    print(f"Status da resposta de login: {login_response.status_code}")
                    print(f"URL final após login: {login_response.url}")
                    print(f"Cookies da sessão: {list(session.cookies.keys())}")
                    
                    # Verifica se a autenticação foi bem-sucedida
                    auth_success = False
                    
                    # Método 1: Verifica cookies de sessão - O Geohab usa Cookies por seção para login
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
                    
                    # Busca o token CSRF
                    csrf_token = None
                    for cookie in session.cookies:
                        if cookie.name == 'XSRF-TOKEN': # Geohab gera token para o Gateway e para o GeoNetwork
                            csrf_token = cookie.value
                            print(f"Token CSRF encontrado: {csrf_token[:20]}...")
                            break
                    
                    # Se não encontrou o token no caminho específico, tenta buscar genericamente
                    if not csrf_token:
                        csrf_token = session.cookies.get('XSRF-TOKEN')
                        if csrf_token:
                            print(f"Token CSRF encontrado (genérico): {csrf_token[:20]}...") #Usar token desse caminho, se tentar usar o token do Gateway a API do GN bloqueia o create do metadado
                    
                    if not csrf_token:
                        print("Aviso: Cookie XSRF-TOKEN não encontrado. Tentando prosseguir sem ele.")
                    
                    gn_headers = {'Accept': 'application/json', 'Referer': GEONETWORK_CATALOG_URL}
                    if csrf_token:
                        gn_headers['X-XSRF-TOKEN'] = csrf_token
                    
                    params = {'publishToAll': 'false'} #Default para tornar o metadado não publicado - a publicação é feita no console do GN
                    files_payload = {'file': ('metadata.xml', xml_payload.encode('utf-8'), 'application/xml')} #A API do GN não aceita xml bruto, precisa "embrulhar" em um arquivo antes de enviar
                    
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
                            success_text = (f"Metadados publicados com sucesso no Geohab!<br><br>"
                                            f"Nome do metadado: {metadata_dict['title']}<br>"
                                            f"UUID: {uuid_criado}<br><br>"
                                            f'Acesse o <a href="https://geohab.cdhu.sp.gov.br/geonetwork/srv/por/catalog.edit#/board">Geohab</a> e finzalize a publicação do metadado!')
                            # MUDANÇA - pedido Daniel
                            self.show_message("Sucesso!", success_text)
                        except:
                            success_text = f"Metadados publicados com sucesso no Geohab!<br><br>Nome do metadado: {metadata_dict['title']}"
                            # MUDANÇA - pedido Daniel
                            self.show_message("Sucesso!", success_text)
                    else:
                        print(f"ERRO do GeoNetwork: {gn_response.status_code} - {gn_response.text}")
                        error_text = f"Falha no envio (Status: {gn_response.status_code}).<br><br>Verifique as suas credenciais ou você não tem permissão.<br>Veja o log do console Python."
                        # MUDANÇA - pedido Daniel
                        self.show_message("Erro no Envio", error_text, icon=QtWidgets.QMessageBox.Critical)
            
            else:
                # O usuário clicou em "Cancel"
                self.iface.messageBar().pushMessage("Info", "Exportação cancelada pelo usuário.", level=Qgis.Info)
                return

        except requests.exceptions.RequestException as e:
            print(f"ERRO DE REDE: {e}")
            # MUDANÇA
            self.show_message("Erro de Rede", f"Não foi possível conectar:<br><br>{e}", icon=QtWidgets.QMessageBox.Critical)

        except Exception as e:
            print(f"ERRO INESPERADO: {e}")
            import traceback
            traceback.print_exc()
            # MUDANÇA - pedido Daniel
            self.show_message("Erro Inesperado", f"Ocorreu um erro no plugin:<br><br>{e}", icon=QtWidgets.QMessageBox.Critical)


    # --------------------------------- FUNÇÃO LOGIN GEOSERVER ---------------------------------- #
    def open_distribution_workflow(self):
        """ Inicia o fluxo de dois passos: Login -> Seleção. """
        
        # Passo 1: Diálogo de Login
        login_dialog = GeoServerLoginDialog(self)
        login_dialog.set_data(self.distribution_data) #021025

        # Apenas se o usuário clicar em "Login" e a autenticação for bem-sucedida...
        if login_dialog.exec_() == QtWidgets.QDialog.Accepted:
            credentials = login_dialog.get_credentials()

            if credentials and 'geoserver_user' in credentials:
                self.distribution_data['geoserver_user'] = credentials['geoserver_user'] #021025

            # Passo 2: Diálogo de Seleção de Camada
            selection_dialog = LayerSelectionDialog(credentials, self)
            # Alimenta o diálogo de seleção com os dados existentes
            selection_dialog.set_data(self.distribution_data)  # 021025

            # Apenas se o usuário preencher e clicar em "OK"...
            if selection_dialog.exec_() == QtWidgets.QDialog.Accepted:
                self.distribution_data.update(selection_dialog.get_data())
                self.update_distribution_button()
                self.iface.messageBar().pushMessage("Sucesso", "Informações de distribuição salvas.", level=Qgis.Success)
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
#from .geoserver_login_dialog import GeoServerLoginDialog
from .layer_selection_dialog import LayerSelectionDialog
from .plugin_config import config_loader
from .unified_login_dialog import UnifiedLoginDialog # <-- Import correto
import pathlib
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject
)

CONTATOS_PREDEFINIDOS = {
    # ... seu dicionário de contatos permanece aqui ...
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
    def __init__(self, parent=None, iface=None):
        """Constructor."""
        super(GeoMetadataDialog, self).__init__(parent)
        self.setupUi(self)

        self.iface = iface
        self.distribution_data = {}

        # --- NOVO: Atributos para a sessão de login unificada ---
        self.api_session = None
        self.last_username = None

        # Configuração inicial da UI
        self.populate_comboboxes()
        self.auto_fill_from_layer()

        # --- MODIFICADO: Conexões de Botões ---
        self.btn_exp_xml.clicked.connect(self.exportar_to_xml)
        self.btn_exp_geo.clicked.connect(self.exportar_to_geo)
        self.btn_salvar.clicked.connect(self.salvar_metadados_sidecar)
        self.btn_login.clicked.connect(self.authenticate)
        self.comboBox_contact_presets.currentIndexChanged.connect(self.on_contact_preset_changed)
        self.btn_distribution_info.clicked.connect(self.open_distribution_workflow)

        # Atualiza o estado inicial dos botões
        self.update_ui_for_login_status()

    # ------------------------------------- NOVA FUNÇÃO DE AUTENTICAÇÃO ---------------------------------- #
    def authenticate(self):
        """
        Abre a dialog de login unificada para obter ou limpar uma sessão autenticada.
        """
        if self.api_session:
            self.api_session = None
            self.iface.messageBar().pushMessage("Info", "Desconectado do Geohab.", level=Qgis.Info, duration=3)
            self.update_ui_for_login_status()
            return

        login_dialog = UnifiedLoginDialog(self)
        if self.last_username:
            login_dialog.set_data({'last_username': self.last_username})

        if login_dialog.exec_():
            self.api_session = login_dialog.get_session()
            self.last_username = login_dialog.get_last_username()
            self.iface.messageBar().pushMessage("Sucesso", f"✅ Conectado ao Geohab como {self.last_username}!", level=Qgis.Success, duration=4)
        else:
            self.api_session = None
        
        self.update_ui_for_login_status()

    # ------------------------------------- NOVA FUNÇÃO PARA ATUALIZAR UI --------------------------------- #
    def update_ui_for_login_status(self):
        """
        Atualiza a interface (botões, etc.) com base no status de login.
        """
        is_logged_in = self.api_session is not None
        self.btn_exp_geo.setEnabled(is_logged_in)
        
        if is_logged_in:
            self.btn_login.setText(f"✅ Conectado ({self.last_username})")
            self.btn_login.setToolTip("Clique para desconectar do Geohab")
        else:
            self.btn_login.setText(" Conectar ao Goehab")
            self.btn_login.setToolTip("Clique para fazer login no Goehab e habilitar a exportação")

    # -------------------------- FUNÇÃO EXPORTAR PARA GEOHAB (TOTALMENTE REFATORADA) --------------------- #
    def exportar_to_geo(self):
        """
        Coleta os dados, gera o XML e o envia para a API do GeoNetwork usando
        a sessão de login previamente estabelecida.
        """
        if not self.api_session:
            self.show_message("Não Autenticado",
                              "Você não está conectado. Por favor, clique em 'Conectar ao Geohab' primeiro.",
                              icon=QtWidgets.QMessageBox.Warning)
            return

        try:
            self.iface.messageBar().pushMessage("Info", "Preparando e enviando metadados...", level=Qgis.Info, duration=3)
            metadata_dict = self.collect_data()
            plugin_dir = os.path.dirname(__file__)
            template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml')
            xml_payload = xml_generator.generate_xml_from_template(metadata_dict, template_path)
            
            gn_urls = config_loader.get_geonetwork_url() 
            geonetwork_api_url = gn_urls.get('records_url')
            geonetwork_catalog_url = gn_urls.get('catalog_url')

            if not geonetwork_api_url or not geonetwork_catalog_url:
                raise ValueError("As URLs do GeoNetwork não estão definidas corretamente no arquivo de configuração.")

            # --- CORREÇÃO FINAL E PRECISA AQUI ---
            # PASSO 1: Visitar o catálogo para garantir que todos os cookies, incluindo os duplicados, estejam na sessão.
            print("Preparando a sessão com o GeoNetwork para obter o token CSRF...")
            self.api_session.get(geonetwork_catalog_url, verify=False)
            
            # PASSO 2: Encontrar o token CSRF CORRETO.
            # Iteramos manualmente para encontrar o token com o path específico do GeoNetwork,
            # resolvendo o erro de cookies duplicados.
            csrf_token = None
            for cookie in self.api_session.cookies:
                if cookie.name == 'XSRF-TOKEN' and 'geonetwork' in cookie.path:
                    csrf_token = cookie.value
                    print(f"Token CSRF específico do GeoNetwork encontrado (path: {cookie.path})")
                    break # Encontramos o que queríamos, podemos parar de procurar

            # PASSO 3: Construir os cabeçalhos.
            headers = {
                'Content-Type': 'application/xml',
                'Accept': 'application/json'
            }
            if csrf_token:
                headers['X-XSRF-TOKEN'] = csrf_token
            else:
                print("AVISO CRÍTICO: O token CSRF específico do GeoNetwork não foi encontrado. A requisição provavelmente falhará.")
            
            # PASSO 4: Enviar o metadado.
            print(f"Enviando metadados para: {geonetwork_api_url}")
            response = self.api_session.put(
                geonetwork_api_url,
                data=xml_payload.encode('utf-8'),
                headers=headers,
                params={'publishToAll': 'false'}
            )
            
            response.raise_for_status()

            # PASSO 5: Processar a resposta.
            if response.status_code in [200, 201]:
                # ... (o resto do tratamento de sucesso permanece o mesmo)
                uuid_criado = "N/A"
                try:
                    response_data = response.json()
                    uuid_criado = response_data.get('@uuid', response_data.get('uuid', 'N/A'))
                except json.JSONDecodeError:
                    print("Resposta não foi JSON, mas o status foi de sucesso.")

                #direct_link = config_loader.get_metadata_view_url(uuid_criado)

                success_text = (f"Metadados enviados com sucesso!<br><br>"
                                f"<b>Título:</b> {metadata_dict['title']}<br>"
                                f"<b>UUID:</b> {uuid_criado}<br><br>"
                                f'Acesse o <a href="{config_loader.get_geonetwork_base_url()}">Geohab</a> para finalizar a publicação.')
                self.show_message("Sucesso!", success_text)
                self.iface.messageBar().pushMessage("Sucesso", f"Metadados '{metadata_dict['title']}' enviados ao Geohab.", level=Qgis.Success, duration=7)
            else:
                raise Exception(f"Resposta inesperada do servidor: Status {response.status_code}")

        except requests.exceptions.HTTPError as e:
            error_text = f"Falha no envio (Status: {e.response.status_code}).<br><br>Verifique suas permissões no Geohab.<br>Detalhe: {e.response.text[:200]}"
            self.show_message("Erro no Envio", error_text, icon=QtWidgets.QMessageBox.Critical)
            print(f"ERRO do GeoNetwork: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.show_message("Erro de Rede", f"Não foi possível conectar ao servidor:<br><br>{e}", icon=QtWidgets.QMessageBox.Critical)
            print(f"ERRO DE REDE: {e}")
        except Exception as e:
            self.show_message("Erro Inesperado", f"Ocorreu um erro no plugin:<br><br>{e}", icon=QtWidgets.QMessageBox.Critical)
            print(f"ERRO INESPERADO: {e}")
            traceback.print_exc()

    # -------------------------- FUNÇÃO EXPORTAR PARA XML --------------------- #

    def exportar_to_xml(self):
        """Coleta dados, gera o XML e pede ao usuário para salvá-lo."""
        
        try:
            metadata_dict = self.collect_data()
            
            plugin_dir = os.path.dirname(__file__)
            template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml')
            
            xml_content = xml_generator.generate_xml_from_template(metadata_dict, template_path)
            
            safe_title = metadata_dict.get('title', 'metadados').replace('_', ' ')
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
            ('Grid | Raster', 'grid'),
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
        data['contact_preset_key'] = self.comboBox_contact_presets.currentData()

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

    # ---------------------------------------- FUNÇÃO GET PATH ----------------------------------------- #
    def get_sidecar_metadata_path(self):
        """
        Obtém o caminho esperado para o arquivo XML sidecar, usando layer.source()
        para compatibilidade com GPKG e SHP, com lógica aprimorada para ZIP.
        """
        layer = self.iface.activeLayer()
        if not layer:
            return None

        source_path = layer.source()
        
        if '|' in source_path:
            base_path = source_path.split('|')[0]
        else:
            base_path = source_path
            
        if 'vsizip' in source_path.lower():
            path_sem_vsizip = source_path.replace('/vsizip/', '')
            zip_index = path_sem_vsizip.lower().find('.zip')
            if zip_index != -1:
                base_path = path_sem_vsizip[:zip_index + 4]

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
            metadata_path = self.get_sidecar_metadata_path()
            if not metadata_path:
                warning_text = (f"A camada '{layer.name()}' não está salva no seu computador!<br><br>"
                                f"A função 'Continuar depois' não pode salvar um metadado para você preencher mais tarde.<br><br>"
                                f"SOLUÇÕES:<br>   • Use 'Exportar para XML' para salvar o metadado, mas desvinculado a camada atual.<br>    • Ou salve a camada '{layer.name()}' no seu computador.")
                self.show_message("Não é possível salvar para 'Continuar depois'", warning_text, icon=QtWidgets.QMessageBox.Warning)
                self.iface.messageBar().pushMessage("Aviso", "A camada não está salva no seu computador.", level=Qgis.Warning, duration=10)
                return
            
            metadata_dict = self.collect_data()
            plugin_dir = os.path.dirname(__file__)
            template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml')
            xml_content = xml_generator.generate_xml_from_template(metadata_dict, template_path)
            metadata_uri = pathlib.Path(metadata_path).as_uri()
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)

            success_text = (f"Pronto!<br><br>"
                            f"Metadados associados à camada '<b>{layer.name()}</b>'.<br>"
                            f"O arquivo foi salvo no mesmo local da camada:<br>"
                            f'<a href="{metadata_uri}">{metadata_path}</a>')
            self.show_message("Metadados associado a camada corretamente!", success_text)
            self.iface.messageBar().pushMessage("Sucesso", f"Metadados associados à camada e salvos em: {metadata_path}", level=Qgis.Success, duration=9)

        except Exception as e:
            print(f"Erro ao salvar arquivo de metadados sidecar: {e}")
            traceback.print_exc()
            error_text = f"Ocorreu um erro ao tentar salvar o arquivo de metadados:<br><br>{e}"
            self.show_message("Erro ao Salvar", error_text, icon=QtWidgets.QMessageBox.Critical)
            self.iface.messageBar().pushMessage("Erro", f"Falha ao salvar metadados: {e}", level=Qgis.Critical)

    # --------------------------------------- FUNÇÃO CARREGAR XML -------------------------------------- #
    def populate_form_from_dict(self, data_dict):
        """
        Preenche os widgets do formulário a partir de um dicionário, armazena os dados
        de distribuição e deduz o preset de contato.
        """
        if not data_dict: return

        self.lineEdit_title.setText(data_dict.get('title', ''))
        try:
            self.spinBox_edition.setValue(int(data_dict.get('edition', '1') or '1'))
        except (ValueError, TypeError):
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

        for key, combo in {
            'status_codeListValue': self.comboBox_status_codeListValue,
            'MD_SpatialRepresentationTypeCode': self.comboBox_MD_SpatialRepresentationTypeCode,
            'LanguageCode': self.comboBox_LanguageCode,
            'characterSet': self.comboBox_characterSet,
            'topicCategory': self.comboBox_topicCategory,
            'hierarchyLevel': self.comboBox_hierarchyLevel,
            'contact_administrativeArea': self.comboBox_contact_administrativeArea,
            'contact_role': self.comboBox_contact_role
        }.items():
            self.set_combobox_by_data(combo, data_dict.get(key))

        self.lineEdit_westBoundLongitude.setText(data_dict.get('westBoundLongitude', ''))
        self.lineEdit_eastBoundLongitude.setText(data_dict.get('eastBoundLongitude', ''))
        self.lineEdit_southBoundLatitude.setText(data_dict.get('southBoundLatitude', ''))
        self.lineEdit_northBoundLatitude.setText(data_dict.get('northBoundLatitude', ''))

        date_creation_str = data_dict.get('date_creation')
        if date_creation_str:
            try:
                dt = QDateTime.fromString(date_creation_str, Qt.ISODateWithMs)
                if not dt.isValid(): dt = QDateTime.fromString(date_creation_str, Qt.ISODate)
                self.dateTimeEdit_date_creation.setDateTime(dt)
            except Exception as e:
                print(f"Erro ao converter data: {e}")

        self.distribution_data['wms_data'] = data_dict.get('wms_data', {})
        self.distribution_data['wfs_data'] = data_dict.get('wfs_data', {})
        self.lineEdit_thumbnail_url.setText(data_dict.get('thumbnail_url', ''))
        self.update_distribution_button()

        found_preset_key = next((
            key for key, data in CONTATOS_PREDEFINIDOS.items() if key != 'nenhum' and
            self.lineEdit_contact_individualName.text() == data.get('contact_individualName') and
            self.lineEdit_contact_organisationName.text() == data.get('contact_organisationName') and
            self.lineEdit_contact_email.text() == data.get('contact_email')
        ), None)

        preset_to_set = found_preset_key if found_preset_key else 'nenhum'
        self.set_combobox_by_data(self.comboBox_contact_presets, preset_to_set)
                
        print("Formulário preenchido com dados de um Metadado existente.")

    def update_distribution_button(self):
        """Atualiza o texto do botão de distribuição com as informações de WMS e WFS."""
        wms_info = self.distribution_data.get('wms_data', {}).get('geoserver_layer_title')
        wfs_info = self.distribution_data.get('wfs_data', {}).get('geoserver_layer_title')
        
        display_text = []
        if wms_info: display_text.append(f"WMS: {wms_info}")
        if wfs_info: display_text.append(f"WFS: {wfs_info}")

        if display_text:
            self.btn_distribution_info.setText(f"🔗 Associado a: {', '.join(display_text)}")
        else:
            self.btn_distribution_info.setText("⚠️ Nenhuma camada associada")

    # --------------------------------- FUNÇÃO MSG ALERTAS ---------------------------------- #
    def show_message(self, title, text, icon=QtWidgets.QMessageBox.Information):
        """Exibe uma janela de diálogo (MessageBox) padronizada para o usuário."""
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(icon)
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(text)
        msg_box.setWindowTitle(title)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg_box.exec_()
        
    # --------------------------------- FUNÇÃO LOGIN GEOSERVER ---------------------------------- #
    def open_distribution_workflow(self):
        """
        Inicia o fluxo de seleção de camada, reaproveitando a sessão de login principal.
        """
        # PASSO 1: VERIFICAR SE O USUÁRIO JÁ ESTÁ LOGADO NO PORTAL
        if not self.api_session:
            self.show_message(
                "Conexão Necessária",
                "Para associar uma camada do GeoServer, por favor, primeiro conecte-se ao portal usando o botão 'Conectar ao Geohab'.",
                icon=QtWidgets.QMessageBox.Information
            )
            return

        # PASSO 2: SE ESTIVER LOGADO, ABRE A JANELA DE SELEÇÃO PASSANDO A SESSÃO
        # A LayerSelectionDialog agora receberá a sessão, não mais as credenciais.
        selection_dialog = LayerSelectionDialog(self.api_session, self)
        
        # Alimenta o diálogo de seleção com os dados já existentes
        selection_dialog.set_data(self.distribution_data)

        # Apenas se o usuário preencher e clicar em "OK"...
        if selection_dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.distribution_data.update(selection_dialog.get_data())
            self.update_distribution_button()
            self.iface.messageBar().pushMessage("Sucesso", "Informações de distribuição salvas.", level=Qgis.Success)
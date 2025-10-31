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
import traceback
import re
import unicodedata
import pathlib
import sys
import subprocess
try:
    import psycopg2
except ImportError:
    psycopg2 = None

# --- 2. Imports de Bibliotecas de Terceiros ---
import requests
from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget, QMessageBox
from qgis.PyQt.QtCore import Qt, QDateTime, QSize
from qgis.PyQt.QtGui import QPixmap, QIcon
from qgis.PyQt.QtWidgets import QSizePolicy
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject
)

# --- 3. Imports de Módulos Locais do Plugin ---
from . import xml_generator, xml_parser, resources
from .layer_selection_dialog import LayerSelectionDialog
from .plugin_config import config_loader
from .unified_login_dialog import UnifiedLoginDialog
from .styles import STYLE_SHEET

# --- Constantes e Configurações ---
CONTATOS_PREDEFINIDOS = {
    'cdhu': { 'uuid': 'b98c4847-4d5c-43e1-a5eb-bd0228f6903a', 'contact_individualName': 'CDHU', 'contact_organisationName': 'Companhia de Desenvolvimento Habitacional e Urbano', 'contact_positionName': '/', 'contact_phone': '+55 11 2505-2479', 'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé', 'contact_city': 'São Paulo', 'contact_postalCode': '01014-930', 'contact_country': 'Brasil', 'contact_email': 'geo@cdhu.sp.gov.br', 'contact_administrativeArea': 'SP', 'contact_role': 'owner' },
    'dpdu': { 'uuid': 'a44bfd3a-a9f4-4caf-ba04-6ca36ab44111', 'contact_individualName': 'DPDU', 'contact_organisationName': 'Diretoria de Planejamento e Desenvolvimento Urbano', 'contact_positionName': '/', 'contact_phone': '+55 11 2505-2553', 'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 8º andar - Bloco 2', 'contact_city': 'São Paulo', 'contact_postalCode': '01014-930', 'contact_country': 'Brasil', 'contact_email': 'hub_habitacao@cdhu.sp.gov.br', 'contact_administrativeArea': 'SP', 'contact_role': 'processor' },
    'ssaru': { 'uuid': '648b9e9f-5b88-4e50-8cce-efa78199515e', 'contact_individualName': 'SSARU', 'contact_organisationName': 'Superintendência Social de Ação em Recuperação Urbana', 'contact_positionName': '/', 'contact_phone': '+55 11 2505-2352', 'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 7º andar', 'contact_city': 'São Paulo', 'contact_postalCode': '01014-930', 'contact_country': 'Brasil', 'contact_email': 'mapeamento.ssaru@cdhu.sp.gov.br', 'contact_administrativeArea': 'SP', 'contact_role': 'author' },
    'terras': { 'uuid': '14e0f9a4-81a6-430e-9165-8af35481d8ac', 'contact_individualName': 'TERRAS', 'contact_organisationName': 'Superintendência de Terras', 'contact_positionName': '/', 'contact_phone': '+55 11 2505-0000', 'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé, 6º andar - Bloco 5', 'contact_city': 'São Paulo', 'contact_postalCode': '01014-930', 'contact_country': 'Brasil', 'contact_email': 'terras@cdhu.sp.gov.br', 'contact_administrativeArea': 'SP', 'contact_role': 'author' },
    'sphu': { 'uuid': '7d1bd2ec-ceee-4f35-a10c-4c37c37355fe', 'contact_individualName': 'SPHU', 'contact_organisationName': 'Superintendência de Projetos Habitacionais e Urbanos', 'contact_positionName': '/', 'contact_phone': '+55 11 2505-0000', 'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé', 'contact_city': 'São Paulo', 'contact_postalCode': '01014-930', 'contact_country': 'Brasil', 'contact_email': 'sphu@cdhu.sp.gov.br', 'contact_administrativeArea': 'SP', 'contact_role': 'processor' },
    'nenhum': { 'contact_individualName': '', 'contact_organisationName': '', 'contact_positionName': '', 'contact_phone': '', 'contact_deliveryPoint': '', 'contact_city': '', 'contact_postalCode': '', 'contact_country': '', 'contact_email': '', 'contact_administrativeArea': '', 'contact_role': '' }
}

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'GeoMetadata_dialog_base.ui'))

class GeoMetadataDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, iface=None):
        """Construtor."""
        super(GeoMetadataDialog, self).__init__(parent)
        
        # --- Atributos da Classe ---
        self.iface = iface
        self.distribution_data = {}
        self.api_session = None
        #self.last_username = None
        self.auth_cfg_id = None
        self.current_metadata_uuid = None

        # --- Ordem de Construção da UI e Lógica ---
        self._setup_main_window()
        self._build_ui_structure()
        self._setup_connections_and_logic()
        
    
    # --- Métodos de Construção e Configuração da UI (Estrutura) ---
    def _setup_main_window(self):
        """Configura as propriedades da janela principal."""
        self.setWindowIcon(QIcon(":/plugins/geometadata/icon.png"))
        self.setObjectName("GeoMetadataDialog")
        self.setWindowTitle("GeoMetadata | CDHU")
        self.setMinimumSize(1200, 690)
        self.setMaximumSize(1640, 690)
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui_structure(self):
        """Cria e organiza os widgets principais da UI (header, card)."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header_widget = self._create_header()
        main_layout.addWidget(header_widget)
        main_layout.addSpacing(15)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(15, 0, 15, 15)
        form_card = self._create_form_card()
        content_layout.addWidget(form_card)
        main_layout.addLayout(content_layout)

    def _setup_connections_and_logic(self):
        """Conecta os sinais dos widgets e inicializa a lógica da UI."""
        self._setup_button_connections()
        self._setup_login_icons()
        self.populate_comboboxes()
        self.auto_fill_from_layer()
        self.update_ui_for_login_status()

    def _create_header(self):
        """Cria o widget do cabeçalho com o novo estilo de navegação."""
        header_widget = QWidget()
        header_widget.setObjectName("Header")
        layout = QHBoxLayout(header_widget)
        layout.setSpacing(10)

        logo_label = QLabel()
        pixmap = QPixmap(":/plugins/geometadata/img/header_logo.png")
        logo_label.setPixmap(pixmap.scaled(170, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        # --- CRIAÇÃO E CONFIGURAÇÃO DOS BOTÕES ---
        # Botão "Continuar depois"
        self.header_btn_salvar = QPushButton("Continuar depois")
        self.header_btn_salvar.setObjectName("HeaderButtonSave") # Nome para o QSS
        

        # Botão "Exportar Metadado"
        self.header_btn_exp_xml = QPushButton("Exportar Metadado")
        self.header_btn_exp_xml.setObjectName("HeaderButtonXml") 

        # Botão "Exportar para Geohab"
        self.header_btn_exp_geo = QPushButton("Exportar para Geohab")
        self.header_btn_exp_geo.setObjectName("HeaderButtonGeo") 

        # Botão "Associar Camada"
        self.header_btn_distribution_info = QPushButton("Associar Camada")
        self.header_btn_distribution_info.setObjectName("HeaderButtonAddLayer")

        # Botão "Entrar" (Login)
        self.header_btn_login = QPushButton()
        self.header_btn_login.setObjectName("ConnectButton")
        
        # --- CONFIGURAÇÃO DO TAMANHO DO ÍCONE ---
        icon_size = QSize(21, 21)
        self.header_btn_salvar.setIconSize(icon_size)
        self.header_btn_exp_xml.setIconSize(icon_size)
        self.header_btn_exp_geo.setIconSize(icon_size)
        self.header_btn_distribution_info.setIconSize(icon_size)

        # --- Montagem do Layout ---
        layout.addWidget(logo_label)
        layout.addWidget(self.header_btn_exp_xml)
        layout.addWidget(self.header_btn_salvar)        
        layout.addWidget(self.header_btn_exp_geo)
        layout.addWidget(self.header_btn_distribution_info)  
        layout.addStretch()
        layout.addWidget(self.header_btn_login)

        
        return header_widget
        
    def _create_distribution_display_panel(self):
        """Cria o QGroupBox para exibir as camadas associadas."""
        
        # 1. Contêiner principal
        container = QtWidgets.QGroupBox("Camadas Associadas")
        container_layout = QtWidgets.QVBoxLayout(container)
        
        # 2. Slot de exibição para WMS
        self.wms_display_widget = self._create_badge_placeholder("WMS")
        self.wms_clear_button = self.wms_display_widget.clear_button
        container_layout.addWidget(self.wms_display_widget)
        
        # 3. Slot de exibição para WFS
        self.wfs_display_widget = self._create_badge_placeholder("WFS")
        self.wfs_clear_button = self.wfs_display_widget.clear_button
        container_layout.addWidget(self.wfs_display_widget)
        
        return container

    def clear_wms_data(self):
        """Limpa os dados de associação WMS e atualiza a UI."""
        if 'wms_data' in self.distribution_data:
            self.distribution_data['wms_data'] = {}
        
        self.update_distribution_display()
        self.iface.messageBar().pushMessage("Info", "Associação WMS removida.", level=Qgis.Info, duration=3)

    def clear_wfs_data(self):
        """Limpa os dados de associação WFS e atualiza a UI."""
        if 'wfs_data' in self.distribution_data:
            self.distribution_data['wfs_data'] = {}
            
        self.update_distribution_display()
        self.iface.messageBar().pushMessage("Info", "Associação WFS removida.", level=Qgis.Info, duration=3)

    def _create_badge_placeholder(self, service_type):
        """Função auxiliar para criar a estrutura de um slot de exibição (ícone + texto)."""
        
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Ícone do globo
        icon_label = QLabel()
        icon_pixmap = QPixmap(":/plugins/geometadata/img/globe.svg")
        icon_label.setPixmap(icon_pixmap.scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        # --- NOVO BOTÃO DE LIMPAR ---
        self.icon_clear = QIcon(":/plugins/geometadata/img/clear_icon.svg")
        clear_button = QPushButton(self.icon_clear, "")
        clear_button.setObjectName("ClearButton") # Para estilização QSS
        clear_button.setFixedSize(10, 10)
        clear_button.setToolTip(f"Remover associação {service_type}")

        # Label para o badge (será estilizado via QSS)
        badge_label = QLabel(service_type)
        badge_label.setObjectName(f"{service_type.lower()}_badge") # Ex: wms_badge, wfs_badge
        badge_label.setAlignment(Qt.AlignCenter)
        
        # Label para o nome da camada
        layer_name_label = QLabel("<i>Nenhuma camada associada.</i>")
        layer_name_label.setWordWrap(True)
        
        layout.addWidget(icon_label)
        layout.addWidget(badge_label)
        layout.addWidget(layer_name_label, 1) # O '1' faz ele expandir
        layout.addWidget(clear_button)
        
        # Armazena referências para atualização futura
        widget.badge_label = badge_label
        widget.layer_name_label = layer_name_label
        widget.clear_button = clear_button
        
        return widget

    def _create_form_card(self):
        """
        Cria o card principal, carrega o formulário e injeta o painel de distribuição
        no layout do contêiner do formulário.
        """
        card_widget = QWidget()
        card_widget.setProperty("class", "Card")
        card_layout = QVBoxLayout(card_widget)

        # --- 1. CARREGA O FORMULÁRIO DO .UI EM UM CONTÊINER TEMPORÁRIO ---
        self.ui = FORM_CLASS()
        form_container = QWidget() # Este é o widget que será populado.
        self.ui.setupUi(form_container)
        
        # Esconde os botões antigos
        for btn_name in ['btn_exp_xml', 'btn_exp_geo', 'btn_salvar', 'btn_login']:
            if hasattr(self.ui, btn_name):
                getattr(self.ui, btn_name).hide()

        # --- 2. CRIA O PAINEL DE DISTRIBUIÇÃO ---
        distribution_panel = self._create_distribution_display_panel()

        # --- 3. INJETA O PAINEL NO LAYOUT DO CONTÊINER DO FORMULÁRIO ---
        # O QGridLayout é o layout do próprio `form_container`
        target_layout = form_container.layout()
        
        # Verificação de segurança para garantir que o layout existe e é uma grade
        if target_layout and isinstance(target_layout, QtWidgets.QGridLayout):
            # addWidget(widget, linha, coluna, rowSpan, colSpan, alinhamento)
            target_layout.addWidget(distribution_panel, 8, 4, 10, 2, Qt.AlignBottom)
        else:
            print("AVISO CRÍTICO: O widget principal do .ui não tem um QGridLayout aplicado!")
            print("Abra o .ui, clique no fundo e aplique um layout de grade.")

        # Adiciona o contêiner ao card
        card_layout.addWidget(form_container)
        
        return card_widget

    def _setup_button_connections(self):
        """Conecta todos os sinais de widgets a seus respectivos slots."""
        self.header_btn_salvar.clicked.connect(self.save_metadata)
        self.header_btn_exp_xml.clicked.connect(self.exportar_to_xml)
        self.header_btn_exp_geo.clicked.connect(self.exportar_to_geo)
        self.header_btn_login.clicked.connect(self.authenticate)
        self.header_btn_distribution_info.clicked.connect(self.open_distribution_workflow)
        
        self.wms_clear_button.clicked.connect(self.clear_wms_data)
        self.wfs_clear_button.clicked.connect(self.clear_wfs_data)

        self.ui.comboBox_contact_presets.currentIndexChanged.connect(self.on_contact_preset_changed)
        #self.ui.btn_distribution_info.clicked.connect(self.open_distribution_workflow)

    def _setup_login_icons(self):
        """Carrega os ícones de login a partir dos recursos."""
        self.icon_login_ok = QIcon(":/plugins/geometadata/img/login_ok.png")
        self.icon_login_error = QIcon(":/plugins/geometadata/img/login_error.png")
        self.header_btn_login.setIconSize(QSize(20, 20))

    def authenticate(self):
        if self.api_session:
            self.api_session = None
            self.iface.messageBar().pushMessage("Info", "❌ Desconectado do Geohab.", level=Qgis.Info, duration=3)
            self.show_message("Info", "<p style='font-size: 14px; font-weight: bold;'>Desconectado do Geohab!</p>", icon=QtWidgets.QMessageBox.Warning)
            self.update_ui_for_login_status()
            return
        
        # Passa o iface para o construtor
        login_dialog = UnifiedLoginDialog(self, iface=self.iface)
        
        if login_dialog.exec_():
            self.api_session = login_dialog.get_session()
            username = login_dialog.get_username()

            self.iface.messageBar().pushMessage("Sucesso", f"✅ Conectado ao Geohab como {username}.", level=Qgis.Success, duration=4)
            success_text = (
                f"<p style='font-size: 15px; font-weight: bold;'>Conectado ao Geohab!</p>"
                f"<p><b>Usuário:</b> {username}</p>"                
                f"<p style='color: rgba(0, 0, 0, 0.5);'>Você pode Associar camadas e Exportar para Geohab</p>")
            self.show_message("Sucesso!", success_text)
        
        self.update_ui_for_login_status()

    def update_ui_for_login_status(self):
        is_logged_in = self.api_session is not None
        self.header_btn_exp_geo.setEnabled(is_logged_in)
        self.header_btn_distribution_info.setEnabled(is_logged_in)
        
        if is_logged_in:
            try:
                # Pega o nome do usuário que foi salvo durante o processo de login
                username = self.api_session.auth[0] 
            except (AttributeError, IndexError):
                username = "Usuário Conectado"

            self.header_btn_login.setIcon(self.icon_login_ok)
            self.header_btn_login.setText(f" {username}")
            self.header_btn_login.setToolTip("Clique para desconectar")
        else:
            self.header_btn_login.setIcon(self.icon_login_error)
            self.header_btn_login.setText(" ENTRAR")
            self.header_btn_login.setToolTip("Clique para fazer login no Geohab")

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
        
        metadata_title = self.ui.lineEdit_title.text()
        
        # 1. Question para o user.
        question_text = (f"<p style='font-size:14px; font-weight: bold;'>Você deseja realmente exportar o metadado?</p>"
                         f"<p>Nome do metadado: <b>{metadata_title}</b></p>")

        # 2. Captura de resposta.
        reply = QtWidgets.QMessageBox.question(self, 
                                               'Confirmar Exportação', 
                                               question_text, 
                                               QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel, 
                                               QtWidgets.QMessageBox.Cancel)

        # 3. Verifique a resposta. Se não, cancele a operação.
        if reply != QtWidgets.QMessageBox.Ok:
            self.iface.messageBar().pushMessage("Info", "Exportação cancelada pelo usuário.", level=Qgis.Info, duration=3)
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

            # PASSO 1: Visitar o catálogo para garantir que todos os cookies, incluindo os duplicados, estejam na sessão.
            print("Preparando a sessão com o GeoNetwork para obter o token CSRF...")
            self.api_session.get(geonetwork_catalog_url, verify=False)
            
            # PASSO 2: Encontrar o token CSRF CORRETO.
            # Itera manualmente para encontrar o token com o path específico do GeoNetwork,
            # resolção do erro de cookies duplicados.
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
                print(f"Resposta do GeoNetwork (Status {response.status_code}): {response.text}")
                uuid_criado = "N/A"
                try:
                    response_data = response.json()
                    uuid_criado = response_data.get('@uuid', response_data.get('uuid', 'N/A'))
                except json.JSONDecodeError:
                    print("Resposta não foi JSON, mas o status foi de sucesso.")
                #Lógica de UUID do Geohab
                if uuid_criado and uuid_criado != "N/A":
                    # 1. Atualiza o UUID na memória da dialog para uso futuro
                    self.current_metadata_uuid = uuid_criado
                    
                    # 2. Silenciosamente, ressalva o arquivo sidecar com o UUID oficial
                    print(f"Vinculando metadado ao UUID oficial: {uuid_criado}. Ressalvando arquivo sidecar...")
                    self.save_metadata(is_automatic_resave=True)
                direct_link = config_loader.get_metadata_view_url(uuid_criado)
                                #f'Acesse o <a href="{config_loader.get_geonetwork_base_url()}">Geohab</a> para finalizar a publicação.')                

                success_text = (f"<p style='font-size: 15px; font-weight: bold;'>Metadados enviados com sucesso!<p/>"
                                f"<p><b>Nome do metadado:</b> {metadata_dict['title']}<br>"
                                f"<b>UUID:</b> {uuid_criado}</p>"
                                f'<p>Acesse o <a href="{config_loader.get_geonetwork_base_url()}">Geohab</a> para finalizar a publicação.</p>')
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

    def sanitize_filename(self, value):
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
        value = re.sub(r'[^\w\s-]', '', value).strip()
        value = re.sub(r'[-\s]+', '-', value)
        return value

    def exportar_to_xml(self):
        try:
            metadata_dict = self.collect_data()
            plugin_dir = os.path.dirname(__file__)
            template_path = os.path.join(plugin_dir, 'tamplate_mgb20.xml')
            xml_content = xml_generator.generate_xml_from_template(metadata_dict, template_path)
            safe_filename_base = self.sanitize_filename(metadata_dict.get('title', 'metadados'))
            suggested_filename = f"{safe_filename_base}.xml"
            
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Salvar Metadados XML", suggested_filename, "Arquivos XML (*.xml)")
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f: f.write(xml_content)
                self.iface.messageBar().pushMessage("Sucesso", f"Metadados salvos em: {file_path}", level=Qgis.Success, duration=5)
                metadata_uri = pathlib.Path(file_path).as_uri()                
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setWindowTitle("Exportação Concluída")
                msg_box.setText("<p style='font-size: 15px; font-weight: bold;'>Metadados salvos com sucesso!</p>")
                msg_box.setInformativeText(f"<b>Caminho do Arquivo:</b><br> <a href='{metadata_uri}'>{file_path}</a>")
                open_folder_button = msg_box.addButton("Abrir Pasta do Arquivo", QMessageBox.ActionRole)
                msg_box.addButton(QMessageBox.Ok)
                msg_box.exec_()
                if msg_box.clickedButton() == open_folder_button: self.open_folder_and_select_file(file_path)
        except Exception as e:
            traceback.print_exc()
            self.show_message("Erro na Exportação", f"Ocorreu um erro ao gerar o XML:<br><br>{e}", icon=QtWidgets.QMessageBox.Critical)

    def open_folder_and_select_file(self, file_path):
        try:
            path = os.path.normpath(file_path)
            if sys.platform == 'win32': subprocess.run(['explorer', '/select,', path])
            elif sys.platform == 'darwin': subprocess.run(['open', '-R', path])
            else: subprocess.run(['xdg-open', os.path.dirname(path)])
        except Exception as e:
            self.iface.messageBar().pushMessage("Erro", f"Não foi possível abrir o Explorador de arquivos: {e}", level=Qgis.Critical)

    def save_metadata(self, is_automatic_resave=False):
        """
        Salva os metadados no local apropriado: um arquivo sidecar para camadas
        baseadas em arquivo, ou uma tabela no banco de dados para camadas PostgreSQL.
        """
        layer = self.iface.activeLayer()
        if not layer:
            self.show_message("Nenhuma Camada Ativa", "Por favor, selecione uma camada no painel de camadas.", icon=QtWidgets.QMessageBox.Warning)
            return

        if self._is_postgres_layer(layer):
            self._save_metadata_to_db(layer, is_automatic_resave)
        else:
            self._save_metadata_to_sidecar_file(layer, is_automatic_resave)

    def populate_comboboxes(self):
        def populate(combo, options):
            combo.clear()
            for text, data in options:
                combo.addItem(text, data)
        
        populate(self.ui.comboBox_status_codeListValue, [('Arquivo Antigo', 'historicalArchive'), ('Concluído', 'completed'), ('Contínuo', 'onGoing'), ('Em Desenvolvimento', 'underDevelopment'), ('Necessário', 'required'), ('Obsoleto', 'obsolete'), ('Planejado', 'planned')])
        populate(self.ui.comboBox_contact_presets, [('DPDU', 'dpdu'), ('SPHU', 'sphu'), ('SSARU', 'ssaru'), ('TERRAS', 'terras')])
        populate(self.ui.comboBox_MD_SpatialRepresentationTypeCode, [('Vetor', 'vector'), ('Grid | Raster', 'grid'), ('Tabela de texto', 'textTable'), ('Rede triangular irregular (TIN)', 'tin'), ('Modelo estereofónico', 'stereoscopicModel'), ('Vídeo', 'video')])
        populate(self.ui.comboBox_LanguageCode, [('🇧🇷 Português', 'por'), ('🇺🇸 Inglês', 'eng'), ('🇪🇸 Espanhol', 'spa'), ('🇫🇷 Françês', 'fra'), ('🇩🇪 Alemão', 'ger')])
        populate(self.ui.comboBox_characterSet, [('UTF-8', 'utf8')])
        populate(self.ui.comboBox_topicCategory, [('Limites Administrativos', 'boundaries'), ('Planejamento e Cadastro', 'planningCadastre'), ('Sociedade e Cultura', 'society'), ('Infraestrutura', 'structure'), ('Transportes', 'transportation'), ('Localização', 'location'), ('Mapas ou imagens de Satélite', 'imageryBaseMapsEarthCover'), ('Altimetria, Batimetria ou Topografia', 'elevation'), ('Saúde', 'health'), ('Águas Interiores', 'inlandWaters'), ('Econômia', 'economy'), ('Biotipos', 'biota'), ('Climatologia ou Meteorologia', 'climatologyMeteorologyAtmosphere'), ('Informação GeoCientífica', 'geoscientificInformation'), ('Informação Militar', 'intelligenceMilitary'), ('Oceanos', 'oceans'), ('Infraestruturas de Comunicação', 'utilitiesCommunication'), ('Agricultura, pesca ou pecuária', 'farming')])
        populate(self.ui.comboBox_hierarchyLevel, [('Conjunto de dados', 'dataset')])
        populate(self.ui.comboBox_contact_role, [('Dono', 'owner'), ('Autor', 'author'), ('Organizador', 'processor'), ('Distribuidor', 'distributor'), ('Depositário', 'custodian'), ('Fornecedor de recurso', 'resourceProvider'), ('Investigador principal', 'principalInvestigator'), ('Originador', 'originator'), ('Ponto de contato', 'pointOfContact'), ('Publicador', 'publisher'), ('Utilizador', 'user')])
        populate(self.ui.comboBox_contact_administrativeArea, [('São Paulo', 'SP'), ('Acre', 'AC'), ('Alagoas', 'AL'), ('Amapá', 'AP'), ('Amazonas', 'AM'), ('Bahia', 'BA'), ('Ceará', 'CE'), ('Distrito Federal', 'DF'), ('Espírito Santo', 'ES'), ('Goiás', 'GO'), ('Maranhão', 'MA'), ('Mato Grosso', 'MT'), ('Mato Grosso do Sul', 'MS'), ('Minas Gerais', 'MG'), ('Pará', 'PA'), ('Paraíba', 'PB'), ('Paraná', 'PR'), ('Pernambuco', 'PE'), ('Piauí', 'PI'), ('Rio de Janeiro', 'RJ'), ('Rio Grande do Norte', 'RN'), ('Rio Grande do Sul', 'RS'), ('Rondônia', 'RO'), ('Roraima', 'RR'), ('Santa Catarina', 'SC'), ('Sergipe', 'SE'), ('Tocantins', 'TO')])

    def sanitize_title(self, value):
        if not value: return ""
        title = value.replace('_', ' ').replace('-', ' ')
        title = re.sub(r'[^a-zA-Z0-9À-ÿ\s]', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        return title
    
    def auto_fill_from_layer(self):
        layer = self.iface.activeLayer()
        if not layer: return

        data_from_xml = None
        
        if self._is_postgres_layer(layer):
            xml_content = self._load_metadata_from_db(layer)
            if xml_content:
                # Assume que seu parser pode receber uma string de XML diretamente
                data_from_xml = xml_parser.parse_xml_to_dict(xml_content, is_string=True)
        else:
            # Lógica de arquivo existente
            metadata_path = self.get_sidecar_metadata_path()
            if metadata_path and os.path.exists(metadata_path):
                data_from_xml = xml_parser.parse_xml_to_dict(metadata_path, is_string=False)
        
        if data_from_xml:
            self.populate_form_from_dict(data_from_xml)
            return
        
        self.ui.lineEdit_title.setText(self.sanitize_title(layer.name()))
        source_crs = layer.crs()
        target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        geographic_extent = layer.extent()
        if source_crs.isValid() and target_crs.isValid() and source_crs != target_crs:
            transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
            geographic_extent = transform.transform(geographic_extent)
            
        self.ui.lineEdit_westBoundLongitude.setText(f"{geographic_extent.xMinimum():.6f}")
        self.ui.lineEdit_eastBoundLongitude.setText(f"{geographic_extent.xMaximum():.6f}")
        self.ui.lineEdit_southBoundLatitude.setText(f"{geographic_extent.yMinimum():.6f}")
        self.ui.lineEdit_northBoundLatitude.setText(f"{geographic_extent.yMaximum():.6f}")

    def _is_postgres_layer(self, layer):
        """Verifica se a camada é uma tabela do PostgreSQL."""
        if not layer:
            return False
        return layer.providerType() == 'postgres'

    def _get_postgres_connection_details(self, layer):
        """Extrai os detalhes da conexão, incluindo o ID de autenticação, do data source da camada."""
        uri = layer.source()
        details = {}
        pattern = re.compile(r"(\w+)='([^']*)'|(\w+)=([^\s]+)")
        matches = pattern.findall(uri)
        
        for key_quoted, val_quoted, key_unquoted, val_unquoted in matches:
            key = key_quoted or key_unquoted
            value = val_quoted or val_unquoted
            details[key] = value

        details['f_table_catalog'] = details.get('dbname')
        details['f_table_schema'] = details.get('sschema', details.get('schema', 'public'))
        details['f_table_name'] = details.get('table', '').replace('"', '')
        # A linha mais importante:
        details['authcfg'] = details.get('authcfg') 
        return details

    def _save_metadata_to_db(self, layer, is_automatic_resave=False):
        """Gera o XML e o salva na tabela de metadados do PostgreSQL."""
        if not self._check_auth_system():
            return
    
        if not psycopg2:
            self.show_message("Erro de Dependência", "A biblioteca psycopg2 não foi encontrada.", icon=QtWidgets.QMessageBox.Critical)
            return

        conn_details = self._get_postgres_connection_details(layer)
        if not conn_details.get('f_table_name'):
            self.show_message("Erro", "Não foi possível identificar a tabela da camada.", icon=QtWidgets.QMessageBox.Warning)
            return
            
        if not is_automatic_resave:
            question_text = (f"<p style='font-size:14px; font-weight: bold;'>Você deseja realmente salvar?</p>"
                             f"<p><b>⚠ As informações serão salvas ou atualizadas em:</b><br>"
                             f"{conn_details['f_table_schema']}.qgis_plugin_metadata</p>"
                             f"<p><b>Associado a camada:</b><br>"
                             f"{conn_details['f_table_name']}</p>"
                             f"<p>No banco de dados: <b>{conn_details['f_table_catalog']}</b>.</p>")
            reply = QtWidgets.QMessageBox.question(self, 'Confirmar Salvamento no Banco de Dados', 
                                                   question_text, QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
            if reply != QtWidgets.QMessageBox.Ok:
                self.iface.messageBar().pushMessage("Info", "Operação cancelada.", level=Qgis.Info)
                return

        try:
            # --- LÓGICA DE CONEXÃO CORRIGIDA ---
            conn_details = self._get_postgres_connection_details(layer)
            db_user = conn_details.get('user')
            db_password = conn_details.get('password')
            
            if not db_password and conn_details.get('authcfg'):
                auth_manager = QgsApplication.authManager()
                auth_cfg_id = conn_details['authcfg']
                
                # Pega o objeto de configuração base do mapa que o QGIS fornece
                config = auth_manager.availableAuthMethodConfigs().get(auth_cfg_id)

                if config and auth_manager.loadAuthenticationConfig(auth_cfg_id, config, True):
                    db_user = config.configMap().get('username')
                    db_password = config.configMap().get('password')
                else:
                    self.show_message("Erro de Autenticação", f"Não foi possível carregar a configuração de autenticação '{auth_cfg_id}' do QGIS.", icon=QtWidgets.QMessageBox.Critical)
                    return
                                
            metadata_dict = self.collect_data()
            template_path = os.path.join(os.path.dirname(__file__), 'tamplate_mgb20.xml')
            xml_content = xml_generator.generate_xml_from_template(metadata_dict, template_path)
    
            conn = psycopg2.connect(
                dbname=conn_details.get('dbname'),
                user=db_user,
                password=db_password,
                host=conn_details.get('host'),
                port=conn_details.get('port', 5432)
            )
            cursor = conn.cursor()
            
            sql = """
                INSERT INTO public.qgis_plugin_metadata (f_table_catalog, f_table_schema, f_table_name, metadata_xml)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT qgis_plugin_metadata_unique_layer
                DO UPDATE SET 
                    metadata_xml = EXCLUDED.metadata_xml,
                    owner = DEFAULT,
                    update_time = DEFAULT;
            """
            cursor.execute(sql, (conn_details.get('f_table_catalog'), conn_details['f_table_schema'], conn_details['f_table_name'], xml_content))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            if not is_automatic_resave:
                self.iface.messageBar().pushMessage("Sucesso", f"Metadado salvo para a camada '{layer.name()}'.", level=Qgis.Success, duration=5)
                confirm_text = (f"<p style='font-size:14px; font-weight: bold;'>Metadado Salvo com Sucesso no Banco de dados!</p>"
                    f"<p><b>As informações forão salvas ou atualizadas em:</b><br>"
                    f"{conn_details['f_table_schema']}.qgis_plugin_metadata</p>"
                    f"<p><b>Associado a camada:</b><br>"
                    f"{conn_details['f_table_name']}</p>"
                    f"<p>No banco de dados: <b>{conn_details['f_table_catalog']}</b>.</p>")
                self.show_message(f"Sucesso!", confirm_text)

        except Exception as e:
            self.show_message("Erro de Banco de Dados", f"Não foi possível salvar o metadado:\n\n{e}", icon=QtWidgets.QMessageBox.Critical)
            traceback.print_exc()

    def _load_metadata_from_db(self, layer):
        """Carrega o metadado XML da tabela do PostgreSQL."""
        if not self._check_auth_system():
            return None     
           
        if not psycopg2:
            self.iface.messageBar().pushMessage("Erro", "A biblioteca psycopg2 não foi encontrada.", level=Qgis.Critical)
            return None

        conn_details = self._get_postgres_connection_details(layer)
        if not conn_details.get('f_table_name'):
            return None

        xml_content = None
        try:
            # --- LÓGICA DE CONEXÃO ---
            conn_details = self._get_postgres_connection_details(layer)
            db_user = conn_details.get('user')
            db_password = conn_details.get('password')
            
            if not db_password and conn_details.get('authcfg'):
                auth_manager = QgsApplication.authManager()
                auth_cfg_id = conn_details['authcfg']
                config = auth_manager.availableAuthMethodConfigs().get(auth_cfg_id)

                if config and auth_manager.loadAuthenticationConfig(auth_cfg_id, config, True):
                    db_user = config.configMap().get('username')
                    db_password = config.configMap().get('password')
                else:
                    self.iface.messageBar().pushMessage("Aviso", f"Não foi possível carregar a config de autenticação '{auth_cfg_id}'.", level=Qgis.Warning)
                    # Não retorna, tenta conectar sem senha (pode funcionar para alguns setups)     
                
            conn = psycopg2.connect(
                dbname=conn_details.get('dbname'),
                user=db_user,
                password=db_password,
                host=conn_details.get('host'),
                port=conn_details.get('port', 5432)
            )
            cursor = conn.cursor()
            
            sql = """
                SELECT metadata_xml 
                FROM public.qgis_plugin_metadata 
                WHERE f_table_catalog = %s AND f_table_schema = %s AND f_table_name = %s;
            """
            cursor.execute(sql, (conn_details.get('f_table_catalog'), conn_details['f_table_schema'], conn_details['f_table_name']))
            
            result = cursor.fetchone()
            if result:
                xml_content = result[0]
                print(f"Metadado carregado do banco de dados para a camada '{layer.name()}'.")
                
            cursor.close()
            conn.close()

        except Exception as e:
            self.iface.messageBar().pushMessage("Aviso", f"Não foi possível carregar o metadado do banco de dados: {e}", level=Qgis.Warning, duration=7)
            traceback.print_exc()
            
        return xml_content

    # --- MÉTODO REFATORADO (lógica de arquivo movida para cá) ---
    def _save_metadata_to_sidecar_file(self, layer, is_automatic_resave=False):
        """Salva os metadados como um arquivo XML sidecar para camadas baseadas em arquivo."""
        metadata_path = self.get_sidecar_metadata_path()
        if not metadata_path:
            layer_name = layer.name() if layer else "A camada"
            self.show_message("Não é possível salvar", f"{layer_name}\n A camada não esta salva em um arquivo local.", icon=QtWidgets.QMessageBox.Warning)
            return

        if not is_automatic_resave:
            # ... (lógica de confirmação do usuário para arquivos, como já existia) ...
            reply = QtWidgets.QMessageBox.question(self, 'Confirmar Salvamento', "Deseja salvar/sobrescrever o arquivo de metadado?", 
                                                   QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
            if reply != QtWidgets.QMessageBox.Ok:
                return

        try:
            metadata_dict = self.collect_data()
            template_path = os.path.join(os.path.dirname(__file__), 'tamplate_mgb20.xml')
            xml_content = xml_generator.generate_xml_from_template(metadata_dict, template_path)
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            if not is_automatic_resave:
                self.iface.messageBar().pushMessage("Sucesso!", f"Metadado Salvo para a camada: '{layer.name()}'")

        except Exception as e:
            self.show_message("Erro ao Salvar Arquivo", f"Ocorreu um erro ao salvar o arquivo:\n\n{e}", icon=QtWidgets.QMessageBox.Critical)
            traceback.print_exc()

    def collect_data(self):
        data = {}
        preset_key = self.ui.comboBox_contact_presets.currentData()
        if preset_key and preset_key != 'nenhum': data['uuid'] = CONTATOS_PREDEFINIDOS.get(preset_key, {}).get('uuid')

        data.update({
            'title': self.ui.lineEdit_title.text(),
            'edition': str(self.ui.spinBox_edition.value()),
            'abstract': self.ui.textEdit_abstract.toPlainText(),
            'MD_Keywords': [k.strip() for k in self.ui.lineEdit_MD_Keywords.text().split(',') if k.strip()],
            'spatialResolution_denominator': self.ui.lineEdit_textEdit_spatialResolution_denominator.text(),
            'contact_individualName': self.ui.lineEdit_contact_individualName.text(),
            'contact_organisationName': self.ui.lineEdit_contact_organisationName.text(),
            'contact_positionName': self.ui.lineEdit_contact_positionName.text(),
            'contact_phone': self.ui.lineEdit_contact_phone.text(),
            'contact_deliveryPoint': self.ui.lineEdit_contact_deliveryPoint.text(),
            'contact_city': self.ui.lineEdit_contact_city.text(),
            'contact_postalCode': self.ui.lineEdit_contact_postalCode.text(),
            'contact_country': self.ui.lineEdit_contact_country.text(),
            'contact_email': self.ui.lineEdit_contact_email.text(),
            'dateStamp': self.ui.dateTimeEdit_dateStamp.dateTime().toUTC().toString("yyyy-MM-ddTHH:mm:ss'Z'"),
            'date_creation': self.ui.dateTimeEdit_date_creation.dateTime().toPyDateTime().astimezone().isoformat(),
            'status_codeListValue': self.ui.comboBox_status_codeListValue.currentData(),
            'MD_SpatialRepresentationTypeCode': self.ui.comboBox_MD_SpatialRepresentationTypeCode.currentData(),
            'LanguageCode': self.ui.comboBox_LanguageCode.currentData(),
            'characterSet': self.ui.comboBox_characterSet.currentData(),
            'topicCategory': self.ui.comboBox_topicCategory.currentData(),
            'hierarchyLevel': self.ui.comboBox_hierarchyLevel.currentData(),
            'contact_administrativeArea': self.ui.comboBox_contact_administrativeArea.currentData(),
            'contact_role': self.ui.comboBox_contact_role.currentData(),
            'westBoundLongitude': self.ui.lineEdit_westBoundLongitude.text(),
            'eastBoundLongitude': self.ui.lineEdit_eastBoundLongitude.text(),
            'southBoundLatitude': self.ui.lineEdit_southBoundLatitude.text(),
            'northBoundLatitude': self.ui.lineEdit_northBoundLatitude.text(),
            'contact_preset_key': self.ui.comboBox_contact_presets.currentData(),
            'thumbnail_url': self.ui.lineEdit_thumbnail_url.text(),
            'metadata_uuid': self.current_metadata_uuid
        })
        data.update(self.distribution_data)
        return data

    def on_contact_preset_changed(self):
        preset_key = self.ui.comboBox_contact_presets.currentData()
        contact_data = CONTATOS_PREDEFINIDOS.get(preset_key, {})
        self.ui.lineEdit_contact_individualName.setText(contact_data.get('contact_individualName', ''))
        self.ui.lineEdit_contact_organisationName.setText(contact_data.get('contact_organisationName', ''))
        self.ui.lineEdit_contact_positionName.setText(contact_data.get('contact_positionName', ''))
        self.ui.lineEdit_contact_phone.setText(contact_data.get('contact_phone', ''))
        self.ui.lineEdit_contact_deliveryPoint.setText(contact_data.get('contact_deliveryPoint', ''))
        self.ui.lineEdit_contact_city.setText(contact_data.get('contact_city', ''))
        self.ui.lineEdit_contact_postalCode.setText(contact_data.get('contact_postalCode', ''))
        self.ui.lineEdit_contact_country.setText(contact_data.get('contact_country', ''))
        self.ui.lineEdit_contact_email.setText(contact_data.get('contact_email', ''))
        self.set_combobox_by_data(self.ui.comboBox_contact_administrativeArea, contact_data.get('contact_administrativeArea', ''))
        self.set_combobox_by_data(self.ui.comboBox_contact_role, contact_data.get('contact_role', ''))

    def set_combobox_by_data(self, combo_box, data_value):
        index = combo_box.findData(data_value)
        if index != -1: combo_box.setCurrentIndex(index)

    def get_sidecar_metadata_path(self):
        layer = self.iface.activeLayer()
        if not layer or not layer.source(): return None
        source_path = layer.source()
        base_path = source_path.split('|')[0] if '|' in source_path else source_path
        if 'vsizip' in source_path.lower():
            path_sem_vsizip = re.sub(r'^/vsizip/', '', source_path, flags=re.IGNORECASE)
            zip_index = path_sem_vsizip.lower().find('.zip')
            if zip_index != -1: base_path = path_sem_vsizip[:zip_index + 4]
        if os.path.isfile(base_path): return base_path + ".xml"
        return None
    
    def populate_form_from_dict(self, data_dict):
        if not data_dict: return
        self.current_metadata_uuid = data_dict.get('metadata_uuid')
        self.ui.lineEdit_title.setText(data_dict.get('title', ''))
        try: self.ui.spinBox_edition.setValue(int(data_dict.get('edition', '1') or '1'))
        except (ValueError, TypeError): self.ui.spinBox_edition.setValue(1)
        self.ui.textEdit_abstract.setText(data_dict.get('abstract', ''))
        self.ui.lineEdit_MD_Keywords.setText(','.join(data_dict.get('MD_Keywords', [])))
        self.ui.lineEdit_textEdit_spatialResolution_denominator.setText(data_dict.get('spatialResolution_denominator', ''))
        self.ui.lineEdit_contact_individualName.setText(data_dict.get('contact_individualName', ''))
        self.ui.lineEdit_contact_organisationName.setText(data_dict.get('contact_organisationName', ''))
        self.ui.lineEdit_contact_positionName.setText(data_dict.get('contact_positionName', ''))
        self.ui.lineEdit_contact_phone.setText(data_dict.get('contact_phone', ''))
        self.ui.lineEdit_contact_deliveryPoint.setText(data_dict.get('contact_deliveryPoint', ''))
        self.ui.lineEdit_contact_city.setText(data_dict.get('contact_city', ''))
        self.ui.lineEdit_contact_postalCode.setText(data_dict.get('contact_postalCode', ''))
        self.ui.lineEdit_contact_country.setText(data_dict.get('contact_country', ''))
        self.ui.lineEdit_contact_email.setText(data_dict.get('contact_email', ''))

        for key, combo in {'status_codeListValue': self.ui.comboBox_status_codeListValue, 'MD_SpatialRepresentationTypeCode': self.ui.comboBox_MD_SpatialRepresentationTypeCode, 'LanguageCode': self.ui.comboBox_LanguageCode, 'characterSet': self.ui.comboBox_characterSet, 'topicCategory': self.ui.comboBox_topicCategory, 'hierarchyLevel': self.ui.comboBox_hierarchyLevel, 'contact_administrativeArea': self.ui.comboBox_contact_administrativeArea, 'contact_role': self.ui.comboBox_contact_role}.items():
            self.set_combobox_by_data(combo, data_dict.get(key))

        self.ui.lineEdit_westBoundLongitude.setText(data_dict.get('westBoundLongitude', ''))
        self.ui.lineEdit_eastBoundLongitude.setText(data_dict.get('eastBoundLongitude', ''))
        self.ui.lineEdit_southBoundLatitude.setText(data_dict.get('southBoundLatitude', ''))
        self.ui.lineEdit_northBoundLatitude.setText(data_dict.get('northBoundLatitude', ''))

        date_creation_str = data_dict.get('date_creation')
        if date_creation_str:
            try:
                dt = QDateTime.fromString(date_creation_str, Qt.ISODateWithMs)
                if not dt.isValid(): dt = QDateTime.fromString(date_creation_str, Qt.ISODate)
                self.ui.dateTimeEdit_date_creation.setDateTime(dt)
            except Exception as e: print(f"Erro ao converter data: {e}")

        self.distribution_data['wms_data'] = data_dict.get('wms_data', {})
        self.distribution_data['wfs_data'] = data_dict.get('wfs_data', {})
        self.ui.lineEdit_thumbnail_url.setText(data_dict.get('thumbnail_url', ''))
        self.update_distribution_display()

 # --- ETAPA 2: DEDUÇÃO DO PRESET ---
        # Compara os dados do DICIONÁRIO (data_dict) com os presets.        
        found_preset_key = None
        # Itera sobre cada preset
        for preset_key, preset_data in CONTATOS_PREDEFINIDOS.items():
            if preset_key == 'nenhum': 
                continue

            # Compara alguns campos-chave para ver se há correspondência
            if (data_dict.get('contact_individualName') == preset_data.get('contact_individualName') and
                data_dict.get('contact_organisationName') == preset_data.get('contact_organisationName') and
                data_dict.get('contact_email') == preset_data.get('contact_email')):
                
                found_preset_key = preset_key
                print(f"Dados de contato carregados correspondem ao preset: '{found_preset_key}'")
                break

        # Define a seleção do ComboBox de presets com base no que foi encontrado
        preset_to_set = found_preset_key if found_preset_key else 'nenhum'
        self.set_combobox_by_data(self.ui.comboBox_contact_presets, preset_to_set)
                
        print("Formulário preenchido com dados de um Metadado existente.")

    def show_message(self, title, text, icon=QtWidgets.QMessageBox.Information):
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(icon)
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(text)
        msg_box.setWindowTitle(title)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg_box.exec_()

    def update_distribution_display(self):
        """
        Atualiza os painéis de exibição com as informações das camadas associadas.
        """
        # --- Obter dados de forma segura ---
        wms_data = self.distribution_data.get('wms_data') or {}
        wfs_data = self.distribution_data.get('wfs_data') or {}
        wms_title = wms_data.get('geoserver_layer_name')
        wfs_title = wfs_data.get('geoserver_layer_name')
        
        # --- Atualizar o painel WMS ---
        wms_badge = self.wms_display_widget.badge_label
        if wms_title:
            self.wms_display_widget.layer_name_label.setText(wms_title)
            wms_badge.setProperty("active", True)
            self.wms_clear_button.show()
        else:
            self.wms_display_widget.layer_name_label.setText("<i>Nenhuma camada associada.</i>")
            wms_badge.setProperty("active", False)
            self.wms_clear_button.hide()
        # Força o Qt a reavaliar o estilo do widget
        wms_badge.style().unpolish(wms_badge)
        wms_badge.style().polish(wms_badge)

        # --- Atualizar o painel WFS ---
        wfs_badge = self.wfs_display_widget.badge_label
        if wfs_title:
            self.wfs_display_widget.layer_name_label.setText(wfs_title)
            wfs_badge.setProperty("active", True)
            self.wfs_clear_button.show()
        else:
            self.wfs_display_widget.layer_name_label.setText("<i>Nenhuma camada associada.</i>")
            wfs_badge.setProperty("active", False)   
            self.wfs_clear_button.hide()
        wfs_badge.style().unpolish(wfs_badge)
        wfs_badge.style().polish(wfs_badge)                      

    def open_distribution_workflow(self):
        """
        Inicia o fluxo de seleção de camada, reaproveitando a sessão de login principal.
        """
        # PASSO 1: VERIFICAR SE O USUÁRIO JÁ ESTÁ LOGADO NO PORTAL
        if not self.api_session:
            self.show_message("Conexão Necessária", icon=QtWidgets.QMessageBox.Information)
            return

        # PASSO 2: SE ESTIVER LOGADO, ABRE A JANELA DE SELEÇÃO PASSANDO A SESSÃO
        # A LayerSelectionDialog agora receberá a sessão, não mais as credenciais.
        selection_dialog = LayerSelectionDialog(self.api_session, self)
        
        # Alimenta o diálogo de seleção com os dados já existentes
        selection_dialog.set_data(self.distribution_data)

        # Apenas se o usuário preencher e clicar em "OK"...
        if selection_dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.distribution_data.update(selection_dialog.get_data())
            self.update_distribution_display()
            self.iface.messageBar().pushMessage("Sucesso", "Informações de distribuição salvas.", level=Qgis.Success)

    def _check_auth_system(self):
        """
        Verifica se o sistema de autenticação do QGIS está funcional.
        Se não estiver, informa o usuário e retorna False.
        """
    
        auth_manager = QgsApplication.authManager()
        if auth_manager.isDisabled():
            title = "Sistema de Autenticação do QGIS Desabilitado"
            message = (
                "<p>Seu plugin GeoMetadata detectou que o sistema de autenticação do QGIS "
                "nesta instalação está desabilitado ou corrompido. Isso impede o acesso "
                "seguro a bancos de dados.</p>"
                "<p><b>Este não é um erro do plugin</b>, mas sim da instalação do QGIS. "
                "A causa mais provável é uma instalação incompleta.</p>"
                "<p><b>Solução Recomendada:</b><br>"
                "1. Feche o QGIS.<br>"
                "2. Desinstale esta versão específica do QGIS.<br>"
                "3. Abra um CDA ou reinstale-a usando o instalador oficial e executando como administrador.</p>"
            )
            self.show_message(title, message, icon=QtWidgets.QMessageBox.Critical)
            return False
        return True
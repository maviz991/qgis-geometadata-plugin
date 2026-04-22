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
from qgis.PyQt.QtCore import Qt, QDateTime, QSize, QUrl 
from qgis.PyQt.QtGui import QDesktopServices, QCursor
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
from .core import xml_generator, xml_parser
from .ui.form_manager import FormManager
from .core.metadata_service import MetadataService
from .core.persistence_service import PersistenceService
from . import resources
from .ui.layer_selection_dialog import LayerSelectionDialog
from .core.plugin_config import config_loader
from .ui.unified_login_dialog import UnifiedLoginDialog
from .ui.entra_login_dialog import EntraLoginDialog
from .ui.styles import STYLE_SHEET


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'GeoMetadata_dialog_base.ui'))

class GeoMetadataDialog(QtWidgets.QDialog):
    def __init__(self, iface, plugin_instance, parent=None):
        """Construtor."""
        super(GeoMetadataDialog, self).__init__(parent)
        
        # --- Atributos da Classe ---
        self.iface = iface
        self.plugin = plugin_instance
        self.distribution_data = {}
        self.auth_cfg_id = None
        self.current_metadata_uuid = None
        self.form_is_dirty = False
        self._load_contacts()

        palette = iface.mainWindow().palette()
        base_color = palette.color(palette.Base)
        luminance = (0.299 * base_color.red() + 0.587 * base_color.green() + 0.114 * base_color.blue())
        if luminance < 128:
            self.setProperty("theme", "dark")
            #print("GeoMetadata: Tema escuro detectado. Aplicando estilos escuros.")
        else:
            self.setProperty("theme", "light") # Opcional, para clareza
            #print("GeoMetadata: Tema claro detectado.")

        # --- Ordem de Construção da UI e Lógica ---
        self._setup_main_window()
        self._build_ui_structure()
        
        # --- Inicialização dos Microsserviços e Bridge (AGORA SEGUROS) ---
        self.metadata_service = MetadataService(self.plugin.api_session)
        self.persistence_service = PersistenceService(self.iface)
        self.form_manager = FormManager(self.ui, self, self.contatos_predefinidos)

        self._setup_connections_and_logic()
        self.setStyleSheet(STYLE_SHEET)

        # --- CONFIGURAÇÃO DO LINK DE SUPORTE ---
        # 1. Define o texto como Rich Text para permitir links HTML
        self.ui.label_support_link.setTextFormat(Qt.RichText)
        self.ui.label_support_link.setText(
            '<a href="https://stor.cdhu.sp.gov.br/geo/publico/html/guide_user.html" style="color: #888; text-decoration: none;">'
            'Precisa de ajuda? Acesse o Manual do Usuário'
            '</a>'
        )
        # 2. Permite que o QLabel interaja com os links
        self.ui.label_support_link.setOpenExternalLinks(True)
        self.ui.label_support_link.setCursor(QCursor(Qt.PointingHandCursor))
        
    def _load_contacts(self):
        """Lê o arquivo contacts.json e carrega os dados em self.contatos_predefinidos."""
        self.contatos_predefinidos = {}
        try:
            import os, json
            contacts_path = os.path.join(os.path.dirname(__file__), 'assets', 'contacts.json')
            with open(contacts_path, 'r', encoding='utf-8') as f:
                self.contatos_predefinidos = json.load(f)
        except Exception as e:
            from qgis.PyQt import QtWidgets
            QtWidgets.QMessageBox.warning(self, "Aviso", f"Erro ao carregar contatos: {e}")

    # --- Métodos de Construção e Configuração da UI (Estrutura) ---
    def _setup_main_window(self):
        """Configura as propriedades da janela principal."""
        self.setWindowIcon(QIcon(":/plugins/geometadata/icon.png"))
        self.setObjectName("GeoMetadataDialog")
        self.setWindowTitle("Geohab Plugin | GeoMetadata")
        self.setMinimumSize(1250, 620)
        #self.setMaximumSize(1640, 800)
        #self.setStyleSheet(STYLE_SHEET)
        #self.resize(1250, 620)

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
        self.update_ui_for_login_status()
        self.auto_fill_from_layer()
        self.update_distribution_display()
        self.form_manager.connect_dirty_signals(self.on_metadata_changed)

    def on_metadata_changed(self):
        pass # Optional logic when metadata becomes dirty


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
        container.setObjectName("DistributionPanel")
        #print(f"DEBUG: Criado QGroupBox com objectName='{container.objectName()}'")
        
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
        layer_name_label.setObjectName("LayerNameLabel")
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

        self.ui.comboBox_contact_presets.currentIndexChanged.connect(self.form_manager.on_contact_preset_changed)
        self.ui.toolButton_set_today.clicked.connect(self._set_dateStamp_to_today)

    def _set_dateStamp_to_today(self):
        """Define o valor do dateTimeEdit_dateStamp para a data e hora atuais."""
        current_datetime = QDateTime.currentDateTime()
        self.ui.dateTimeEdit_dateStamp.setDateTime(current_datetime)

    def _setup_login_icons(self):
        """Carrega os ícones de login a partir dos recursos."""
        self.icon_login_ok = QIcon(":/plugins/geometadata/img/login_ok.png")
        self.icon_login_error = QIcon(":/plugins/geometadata/img/login_error.png")
        self.header_btn_login.setIconSize(QSize(20, 20))

    def authenticate(self):
        """Gerencia o ciclo de login/logout.
        
        Usa Entra ID (MSAL + PKCE) se as credenciais do Azure estiverem configuradas
        no config.json. Caso contrário, usa o método Basic Auth tradicional (fallback).
        """
        # --- LOGOUT ---
        if self.plugin.api_session:
            self.plugin.api_session = None
            self.plugin.auth_username = None
            self.iface.messageBar().pushMessage(
                "Info", "❌ Desconectado do Geohab.",
                level=Qgis.Info, duration=3
            )
            self.show_message(
                "Info",
                "<p style='font-size: 14px; font-weight: bold;'>Desconectado do Geohab!</p>",
                icon=QtWidgets.QMessageBox.Warning
            )
            self.update_ui_for_login_status()
            return

        # --- LOGIN: Entra ID ou Basic Auth ---
        if config_loader.has_entra_id_configured():
            self._authenticate_entra_id()
        else:
            self._authenticate_basic_auth()

    def _authenticate_entra_id(self):
        """Fluxo de login via Microsoft Entra ID (MSAL + PKCE + Bearer Token)."""
        entra_cfg = config_loader.get_entra_id_config()
        login_dialog = EntraLoginDialog(
            client_id=entra_cfg["client_id"],
            tenant_id=entra_cfg["tenant_id"],
            scopes=entra_cfg.get("scopes", ["openid", "profile", "email"]),
            parent=self
        )

        if login_dialog.exec_():
            self.plugin.api_session = login_dialog.get_session()
            self.plugin.auth_username = login_dialog.get_username()

            self.iface.messageBar().pushMessage(
                "Sucesso",
                f"✅ Conectado ao Geohab como {self.plugin.auth_username}.",
                level=Qgis.Success, duration=4
            )
            self.show_message(
                "Sucesso!",
                f"<p style='font-size: 15px; font-weight: bold;'>Conectado ao Geohab!</p>"
                f"<p><b>Usuário:</b> {self.plugin.auth_username}</p>"
                f"<p style='color: rgba(0,0,0,0.5);'>Você pode Associar camadas e Exportar para Geohab</p>"
            )

        self.update_ui_for_login_status()

    def _authenticate_basic_auth(self):
        """Fluxo de login via Basic Auth (método legado — fallback enquanto Entra ID não está configurado)."""
        login_dialog = UnifiedLoginDialog(self, iface=self.iface)

        if login_dialog.exec_():
            self.plugin.api_session = login_dialog.get_session()
            self.plugin.auth_username = login_dialog.get_username()

            self.iface.messageBar().pushMessage(
                "Sucesso",
                f"✅ Conectado ao Geohab como {self.plugin.auth_username}.",
                level=Qgis.Success, duration=4
            )
            self.show_message(
                "Sucesso!",
                f"<p style='font-size: 15px; font-weight: bold;'>Conectado ao Geohab!</p>"
                f"<p><b>Usuário:</b> {self.plugin.auth_username}</p>"
                f"<p style='color: rgba(0,0,0,0.5);'>Você pode Associar camadas e Exportar para Geohab</p>"
            )

        self.update_ui_for_login_status()

    def update_ui_for_login_status(self):
        """Atualiza botões e ícone do header conforme o estado de login."""
        is_logged_in = self.plugin.api_session is not None
        self.header_btn_exp_geo.setEnabled(is_logged_in)
        self.header_btn_distribution_info.setEnabled(is_logged_in)
        
        if is_logged_in:
            # Usa auth_username (genérico para Entra ID e Basic Auth)
            username = self.plugin.auth_username or "Usuário Conectado"
            self.header_btn_login.setIcon(self.icon_login_ok)
            self.header_btn_login.setText(f" {username}")
            self.header_btn_login.setToolTip("Clique para desconectar")
        else:
            self.header_btn_login.setIcon(self.icon_login_error)
            self.header_btn_login.setText(" ENTRAR")
            self.header_btn_login.setToolTip("Clique para fazer login no Geohab")

    def exportar_to_xml(self):
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
            QtWidgets.QMessageBox.critical(self, 'Erro', f'Falha ao exportar XML: {e}')

    def exportar_to_geo(self):
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
            QtWidgets.QMessageBox.critical(self, 'Erro', f'Falha no GeoNetwork: {e}')

    def save_metadata(self, is_automatic_resave=False):
        """Usa o PersistenceService para salvar no DB ou XML Sidecar."""
        if not is_automatic_resave and not self.form_manager.validate_form(): return
        
        metadata_dict = self.form_manager.collect_data()
        layer = self.iface.activeLayer()
        import os
        template_path = os.path.join(os.path.dirname(__file__), 'assets', 'tamplate_mgb20.xml')
        cdhu_data = self.contatos_predefinidos.get('cdhu', {})
        
        success = self.persistence_service.save(layer, metadata_dict, template_path, cdhu_data, is_automatic_resave, self)
        if success:
            self.form_manager.set_is_dirty(False)

    def sanitize_title(self, value):
        if not value: return ""
        title = value.replace('_', ' ').replace('-', ' ')
        title = re.sub(r'[^a-zA-Z0-9À-ÿ\s]', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        return title
    
    def auto_fill_from_layer(self):
        """Tenta preencher o formulário usando os metadados associados à camada."""
        layer = self.iface.activeLayer()
        if not layer:
            return
            
        xml_content = self.persistence_service.load(layer)
        if xml_content:
            data_dict = xml_parser.parse_xml_to_dict(xml_content, is_string=True)
            self.form_manager.populate_form_from_dict(data_dict)
            self.form_manager.set_is_dirty(False)
            
        self.update_distribution_display()

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
        if not self.plugin.api_session:
            self.show_message("Conexão Necessária", icon=QtWidgets.QMessageBox.Information)
            return

        # PASSO 2: SE ESTIVER LOGADO, ABRE A JANELA DE SELEÇÃO PASSANDO A SESSÃO
        # A LayerSelectionDialog agora receberá a sessão, não mais as credenciais.
        selection_dialog = LayerSelectionDialog(self.plugin.api_session, self)
        
        # Alimenta o diálogo de seleção com os dados já existentes
        selection_dialog.set_data(self.distribution_data)

        # Apenas se o usuário preencher e clicar em "OK"...
        if selection_dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.distribution_data.update(selection_dialog.get_data())
            self.update_distribution_display()
            self.iface.messageBar().pushMessage("Sucesso", "Informações de distribuição salvas.", level=Qgis.Success)

    # GeoMetadata_dialog.py -> adicione este método à classe

    def reject(self):
        """
        Sobrescreve o comportamento padrão da tecla ESC.
        
        Em vez de fechar a janela diretamente, este método chama self.close(),
        que por sua vez acionará o nosso closeEvent(). Isso garante que a
        verificação de alterações não salvas seja executada tanto para a tecla ESC
        quanto para o botão 'X' da janela.
        """
        self.close()

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

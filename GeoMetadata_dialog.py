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
from qgis.PyQt import QtWidgets, QtCore
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QWidget, QMessageBox, QToolButton, QMenu, QAction, QSizePolicy,
    QStackedWidget, QApplication, QStyledItemDelegate, QStyle
)
from qgis.PyQt.QtCore import Qt, QDateTime, QSize, QUrl, QTimer, QEvent, QStringListModel, QRect
from qgis.PyQt.QtGui import QDesktopServices, QCursor, QPixmap, QIcon, QColor, QPainter
from lxml import etree as ET
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
from .ui.dynamic_form import DynamicForm
from .core.metadata_service import MetadataService
from .core.persistence_service import PersistenceService
from . import resources
from .core.plugin_config import config_loader
from .ui.unified_login_dialog import UnifiedLoginDialog
from .ui.entra_login_dialog import EntraLoginDialog
from .ui.styles import get_stylesheet
from .ui.geoserver_panel import GeoServerPanel
from .ui.home_panel import HomePanel


# --- 4. Helpers de Estilo ---
class CustomHeightDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, height=30, font_size=9):
        super().__init__(parent)
        self.forced_height = height
        self.forced_font_size = font_size

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(self.forced_height)
        return size

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 1. Fundo (Hover ou Seleção)
        is_selected = option.state & QStyle.State_Selected
        is_hovered  = option.state & QStyle.State_MouseOver
        
        if is_selected or is_hovered:
            # Cor de fundo da combo (cinza claro)
            painter.fillRect(option.rect, QColor("#f5f5f5"))
            # Borda interna sutil
            painter.setPen(QColor("#d1d5db"))
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
        else:
            painter.fillRect(option.rect, QColor("#ffffff"))

        # 2. Texto
        painter.setPen(QColor("#1e293b"))
        font = option.font
        font.setPointSize(self.forced_font_size)
        if is_selected:
            font.setWeight(600)
        painter.setFont(font)
        
        # Margem para o texto
        text_rect = option.rect.adjusted(10, 0, -10, 0)
        display_text = index.data(Qt.DisplayRole)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, display_text)
        
        painter.restore()
class NavButton(QPushButton):
    """
    Botão de navegação do header — hover e estado ativo via setStyleSheet()
    direto no widget. Sem seletores QSS de propriedade, sem polish().
    """

    _HOVER_LIGHT  = "color:#6d7075;background:#f8fafc;border-bottom:3px solid #cbd5e1;"
    _ACTIVE_LIGHT = "color:#e5222d;background:transparent;border-bottom:3px solid #e5222d;font-weight:700;"
    _HOVER_DARK   = "color:#94a3b8;background:#273549;border-bottom:3px solid #475569;"
    _ACTIVE_DARK  = "color:#38bdf8;background:transparent;border-bottom:3px solid #38bdf8;font-weight:700;"

    _active = None  # botão com menu atualmente aberto

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._nav_menu = None
        self._hovered = False
        self._nav_active = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._maybe_close)
        self.setAttribute(Qt.WA_Hover, True)

    # ------------------------------------------------------------------
    def _is_dark(self):
        w = self.window()
        return bool(w and w.property("theme") == "dark")

    def _update_style(self):
        """Aplica inline style: ativo > hover > padrão (herda do parent stylesheet)."""
        dark = self._is_dark()
        if self._nav_active:
            self.setStyleSheet(self._ACTIVE_DARK if dark else self._ACTIVE_LIGHT)
        elif self._hovered:
            self.setStyleSheet(self._HOVER_DARK if dark else self._HOVER_LIGHT)
        else:
            self.setStyleSheet("")

    def _apply_hover(self, value):
        self._hovered = bool(value)
        self._update_style()

    def set_nav_active(self, value):
        self._nav_active = bool(value)
        self._update_style()

    # ------------------------------------------------------------------
    def set_nav_menu(self, menu):
        self._nav_menu = menu
        menu.installEventFilter(self)

    # ------------------------------------------------------------------
    def _switch_to_me(self):
        """Torna este botao ativo, limpando estado do anterior."""
        prev = NavButton._active
        if prev and prev is not self:
            prev._timer.stop()
            if prev._nav_menu and prev._nav_menu.isVisible():
                prev._nav_menu.hide()
            prev._apply_hover(False)     # limpa hover visual do botao anterior
        NavButton._active = self
        if self._nav_menu and not self._nav_menu.isVisible():
            pos = self.mapToGlobal(self.rect().bottomLeft())
            self._nav_menu.popup(pos)

    # ------------------------------------------------------------------
    def enterEvent(self, event):
        self._timer.stop()
        self._apply_hover(True)
        if self._nav_menu and self.isEnabled():
            self._switch_to_me()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._timer.start()
        self._apply_hover(False)
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    def _maybe_close(self):
        if not (self._nav_menu and self._nav_menu.isVisible()):
            NavButton._active = None
            self._apply_hover(False)
            return
        pos = QCursor.pos()
        if self._nav_menu.rect().contains(self._nav_menu.mapFromGlobal(pos)):
            return
        widget = QApplication.widgetAt(pos)
        if isinstance(widget, NavButton) and widget._nav_menu:
            return
        self._nav_menu.hide()
        self._apply_hover(False)
        NavButton._active = None

    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if obj is self._nav_menu:
            t = event.type()
            if t == QEvent.Enter:
                self._timer.stop()
            elif t == QEvent.Leave:
                self._timer.start()
            elif t == QEvent.MouseMove:
                pos = QCursor.pos()
                widget = QApplication.widgetAt(pos)
                if (isinstance(widget, NavButton)
                        and widget is not self
                        and widget.isEnabled()
                        and widget._nav_menu):
                    widget._switch_to_me()
        return super().eventFilter(obj, event)

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
        img_dir = os.path.join(os.path.dirname(__file__), 'img').replace('\\', '/')
        self.setStyleSheet(get_stylesheet(img_dir))

        # Força estilo Fusion em TODOS os widgets para o QSS ser respeitado no Windows
        from qgis.PyQt.QtWidgets import (
            QComboBox, QSpinBox, QDateTimeEdit, QDateEdit, QTimeEdit,
            QLineEdit, QTextEdit, QPushButton, QToolButton,
            QTabWidget, QTabBar, QStyleFactory
        )
        fusion = QStyleFactory.create("Fusion")
        if fusion:
            for widget_class in (QComboBox, QSpinBox, QDateTimeEdit, QDateEdit,
                                 QTimeEdit, QLineEdit, QTextEdit,
                                 QPushButton, QToolButton,
                                 QTabWidget, QTabBar):
                for w in self.findChildren(widget_class):
                    w.setStyle(fusion)

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
        """Cria e organiza os widgets principais da UI (header + QStackedWidget)."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header_widget = self._create_header()
        main_layout.addWidget(header_widget)
        main_layout.addSpacing(15)

        # --- QStackedWidget: roteador de painéis ---
        self._stacked = QStackedWidget()
        self._stacked.setObjectName("MainStack")

        # Página 0 — Home (ponto de entrada)
        home = HomePanel()
        home.navigate_geonetwork.connect(self._navigate_to_geonetwork)
        home.navigate_geoserver.connect(self._navigate_to_geoserver)
        self._stacked.addWidget(home)

        # Página 1 — GeoNetwork (formulário de metadados)
        self._stacked.addWidget(self._create_geonetwork_panel())

        # Página 2 — GeoServer (publicação de camadas)
        self._stacked.addWidget(self._create_geoserver_panel())

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(15, 0, 15, 15)
        content_layout.addWidget(self._stacked)
        main_layout.addLayout(content_layout)

    def _setup_connections_and_logic(self):
        """Conecta os sinais dos widgets e inicializa a lógica da UI."""
        self._setup_button_connections()
        self._setup_login_icons()
        self.form_manager.populate_comboboxes()
        self.update_ui_for_login_status()
        self.auto_fill_from_layer()
        self.update_distribution_display()
        self._setup_layer_association()
        self._setup_contact_search()
        self.form_manager.connect_dirty_signals(self.on_metadata_changed)

    def on_metadata_changed(self):
        pass # Optional logic when metadata becomes dirty


    def _make_menu(self):
        """QMenu com cantos arredondados sem artefatos no Windows.

        WA_TranslucentBackground + FramelessWindowHint ativam o canal alpha
        da janela nativa, tornando os pixels fora do border-radius transparentes
        em vez de pretos. NoDropShadowWindowHint remove a sombra retangular do OS.
        """
        menu = QMenu(self)
        menu.setObjectName("DropdownMenu")
        menu.setWindowFlags(
            menu.windowFlags()
            | Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint
        )
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        return menu

    def _create_header(self):
        """Cabeçalho com menus hover estilo portal web CDHU.

        Todos os botões de navegação são NavButton (QPushButton):
        - hover sobre o botão → abre o menu não-bloqueante
        - sair do botão/menu → fecha o menu após 180 ms
        - entrar em outro botão → fecha o menu anterior imediatamente
        - click → navega para o painel (SEM reabrir menu)
        """
        header_widget = QWidget()
        header_widget.setObjectName("Header")
        layout = QHBoxLayout(header_widget)
        layout.setSpacing(0)

        # Logo clicável — navega para Home
        pixmap = QPixmap(":/plugins/geometadata/img/header_logo.png")
        scaled = pixmap.scaled(170, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._logo_btn = QPushButton()
        self._logo_btn.setObjectName("LogoButton")
        self._logo_btn.setIcon(QIcon(scaled))
        self._logo_btn.setIconSize(scaled.size())
        self._logo_btn.setFlat(True)
        self._logo_btn.setFixedSize(scaled.size())
        self._logo_btn.setCursor(Qt.PointingHandCursor)

        # --- Menu "Arquivo" ---
        menu_arquivo = self._make_menu()

        self._action_salvar = QAction("Continuar depois", self)
        self._action_salvar.setToolTip("Salva o rascunho localmente sem enviar ao Geohab")
        menu_arquivo.addAction(self._action_salvar)

        btn_arquivo = NavButton("Arquivo")
        btn_arquivo.setObjectName("HeaderDropdownButton")
        btn_arquivo.set_nav_menu(menu_arquivo)

        # --- Menu "GeoNetwork" ---
        menu_geonetwork = self._make_menu()

        # Sub-item de navegação: abre o painel do formulário
        self._action_nav_metadados = QAction("Metadados", self)
        self._action_nav_metadados.setToolTip("Abrir painel de criação e edição de metadados MGB 2.0")
        menu_geonetwork.addAction(self._action_nav_metadados)
        menu_geonetwork.addSeparator()

        self._action_exp_geo = QAction("Exportar para GeoNetwork", self)
        self._action_exp_geo.setToolTip("Publica o metadado no GeoNetwork (requer login)")
        menu_geonetwork.addAction(self._action_exp_geo)

        self._action_distribution = QAction("Associar Camada WMS/WFS", self)
        self._action_distribution.setToolTip("Vincula uma camada publicada ao metadado (requer login)")
        menu_geonetwork.addAction(self._action_distribution)

        self._action_exp_xml = QAction("Exportar Metadado (.xml)", self)
        self._action_exp_xml.setToolTip("Gera e salva o arquivo XML MGB 2.0 no disco")
        menu_geonetwork.addSeparator()
        menu_geonetwork.addAction(self._action_exp_xml)

        self._action_import_metadata = QAction("Importar Metadado (.xml)...", self)
        self._action_import_metadata.setToolTip("Abre um XML MGB 2.0 existente para edição (em breve)")
        self._action_import_metadata.setEnabled(False)  # placeholder
        menu_geonetwork.addAction(self._action_import_metadata)

        self._btn_geonetwork = NavButton("GeoNetwork")
        self._btn_geonetwork.setObjectName("HeaderDropdownButton")
        self._btn_geonetwork.set_nav_menu(menu_geonetwork)

        # --- Menu "GeoServer" ---
        menu_geoserver = self._make_menu()

        # Sub-item de navegação: abre o painel GeoServer
        self._action_nav_geoserver = QAction("GeoServer", self)
        self._action_nav_geoserver.setToolTip("Abrir painel de publicação GeoServer")
        menu_geoserver.addAction(self._action_nav_geoserver)
        menu_geoserver.addSeparator()

        # Aviso de Fase 2 (visual informativo)
        self._action_gs_fase2 = QAction("Em desenvolvimento  —  Fase 2", self)
        self._action_gs_fase2.setEnabled(False)
        menu_geoserver.addAction(self._action_gs_fase2)

        self._action_gs_publish = QAction("Publicar Camada...", self)
        self._action_gs_publish.setToolTip("Publicação GeoServer disponível na Fase 2")
        self._action_gs_publish.setEnabled(False)
        menu_geoserver.addAction(self._action_gs_publish)

        self._btn_geoserver = NavButton("GeoServer")
        self._btn_geoserver.setObjectName("HeaderDropdownButton")
        self._btn_geoserver.set_nav_menu(menu_geoserver)

        # --- Botão de Login ---
        self.header_btn_login = QPushButton()
        self.header_btn_login.setObjectName("ConnectButton")
        self.header_btn_login.setIconSize(QSize(20, 20))

        # --- Montagem ---
        layout.addWidget(self._logo_btn)
        layout.addSpacing(8)
        layout.addWidget(btn_arquivo)
        layout.addWidget(self._btn_geonetwork)
        layout.addWidget(self._btn_geoserver)
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

    def _create_geonetwork_panel(self):
        """Painel GeoNetwork: formulário dinâmico MGB 2.0 + painel de distribuição."""
        panel = QWidget()
        panel.setObjectName("GeoNetworkPanel")
        panel.setProperty("class", "Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- FORMULÁRIO DINÂMICO (QScrollArea sem dependência de .ui) ---
        self._dynamic_form = DynamicForm()
        self.ui = self._dynamic_form   # FormManager acessa via self.ui.widget_name
        layout.addWidget(self._dynamic_form.get_scroll_area(), 1)

        # --- PAINEL DE DISTRIBUIÇÃO (injetado na aba "Recursos associados") ---
        distribution_panel = self._create_distribution_display_panel()
        self.ui.recursos_container.addWidget(distribution_panel)

        return panel

    def _create_geoserver_panel(self):
        """Painel GeoServer: publicação de camadas (placeholder Fase 2)."""
        return GeoServerPanel()

    # ------------------------------------------------------------------
    def _set_active_nav_btn(self, active_btn):
        for btn in (self._btn_geonetwork, self._btn_geoserver):
            btn.set_nav_active(btn is active_btn)

    def _navigate_to_home(self):
        """Navega para a Home (índice 0)."""
        self._stacked.setCurrentIndex(0)
        self._set_active_nav_btn(None)  # logo é Home — nenhum botão nav ativo

    def _navigate_to_geonetwork(self):
        """Navega para o painel GeoNetwork (índice 1)."""
        self._stacked.setCurrentIndex(1)
        self._set_active_nav_btn(self._btn_geonetwork)

    def _navigate_to_geoserver(self):
        """Navega para o painel GeoServer (índice 2)."""
        self._stacked.setCurrentIndex(2)
        self._set_active_nav_btn(self._btn_geoserver)

    def _setup_button_connections(self):
        """Conecta sinais do header (QActions) e widgets internos do formulário."""
        # --- Header: menu Arquivo ---
        self._action_salvar.triggered.connect(self.save_metadata)

        # --- Header: menu GeoNetwork ---
        self._action_nav_metadados.triggered.connect(self._navigate_to_geonetwork)
        self._action_exp_xml.triggered.connect(self.exportar_to_xml)
        self._action_exp_geo.triggered.connect(self.exportar_to_geo)
        self._action_distribution.triggered.connect(self.open_distribution_workflow)
        # _action_import_metadata: placeholder (não conectado ainda)

        # --- Header: menu GeoServer ---
        self._action_nav_geoserver.triggered.connect(self._navigate_to_geoserver)

        # --- Header: logo navega para Home ---
        self._logo_btn.clicked.connect(self._navigate_to_home)

        # --- Header: botão de login ---
        self.header_btn_login.clicked.connect(self.authenticate)

        # --- Painel de distribuição ---
        self.wms_clear_button.clicked.connect(self.clear_wms_data)
        self.wfs_clear_button.clicked.connect(self.clear_wfs_data)

        # --- Formulário dinâmico ---
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

        self.form_manager.populate_comboboxes()
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

        self.form_manager.populate_comboboxes()
        self.update_ui_for_login_status()

    def update_ui_for_login_status(self):
        """Habilita/desabilita QActions de GeoNetwork e GeoServer; atualiza botão de login."""
        is_logged_in = self.plugin.api_session is not None
        tip_locked = "Faça login para usar esta função"

        # --- GeoNetwork ---
        self._action_exp_geo.setEnabled(is_logged_in)
        self._action_distribution.setEnabled(is_logged_in)
        self._action_exp_geo.setToolTip(
            "Publica o metadado no GeoNetwork" if is_logged_in else tip_locked)
        self._action_distribution.setToolTip(
            "Vincula uma camada publicada ao metadado" if is_logged_in else tip_locked)

        # --- GeoServer (placeholder — desabilitado até Fase 2) ---
        self._action_gs_publish.setEnabled(False)
        self._action_gs_publish.setToolTip("Publicação GeoServer disponível na Fase 2")

        if is_logged_in:
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
        Navega para a aba de associação de Recursos (índice 4).
        """
        self._navigate_to_geonetwork()
        self.ui._tabs.setCurrentIndex(4)

    # --- INTEGRAÇÃO DA SELEÇÃO DE CAMADAS ---
    def _setup_layer_association(self):
        self.completer_model = QtCore.QStringListModel()
        self.completer = QtWidgets.QCompleter(self.completer_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self.completer.setFilterMode(Qt.MatchContains)
        
        # Estilização forçada para o Popup do Completer
        completer_style = """
            QAbstractItemView#CompleterPopup {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                outline: none;
            }
        """
        
        popup = self.completer.popup()
        popup.setObjectName("CompleterPopup")
        popup.setMouseTracking(True)
        popup.setStyleSheet(completer_style)
        
        # Uso do Delegate global para forçar altura, hover e fonte
        self._delegate1 = CustomHeightDelegate(popup, height=30, font_size=9)
        popup.setItemDelegate(self._delegate1)
        
        self.ui.lineEdit_layer_search.setCompleter(self.completer)

        # Configurar UI combo de serviço
        self.icon_wms = QIcon(":/plugins/geometadata/img/wms_icon.png")
        self.icon_wfs = QIcon(":/plugins/geometadata/img/wfs_icon.png")
        self.ui.comboBox_service_type.addItem(self.icon_wms, "WMS [ Mapa ]", "wms")
        self.ui.comboBox_service_type.addItem(self.icon_wfs, "WFS [ Vetor ]", "wfs")

        # Conectar sinais
        self.ui.comboBox_service_type.currentIndexChanged.connect(self._fetch_layers)
        self.completer.activated.connect(self._on_layer_selected)
        self.ui.btn_addservice.clicked.connect(self._add_service_selection)

        # Dados
        self.distribution_layers_cache = []
        self.layer_data_map = {}
        self.selected_layer_data = None

    def _fetch_layers(self):
        service = self.ui.comboBox_service_type.currentData()
        self.distribution_layers_cache.clear()
        self.layer_data_map.clear()
        self.completer_model.setStringList([])
        self.ui.lineEdit_layer_search.clear()
        self.selected_layer_data = None

        if not service:
            self.ui.lineEdit_layer_search.setEnabled(False)
            return

        if not self.plugin.api_session:
            self.show_message("Sessão não iniciada", "Faça login no Geohab primeiro.", icon=QtWidgets.QMessageBox.Warning)
            self.ui.comboBox_service_type.blockSignals(True)
            self.ui.comboBox_service_type.setCurrentIndex(0)
            self.ui.comboBox_service_type.blockSignals(False)
            return

        self.ui.lineEdit_layer_search.setText("Carregando...")
        self.ui.lineEdit_layer_search.setEnabled(False)

        geoserver_url = config_loader.get_geoserver_url()
        if service == 'wms':
            url = f"{geoserver_url}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
        else: # wfs
            url = f"{geoserver_url}/ows?service=WFS&version=1.1.0&request=GetCapabilities"

        try:
            response = self.plugin.api_session.get(url, timeout=20, verify=False)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            layers_found = []
            
            if service == 'wms':
                ns = {'wms': 'http://www.opengis.net/wms'}
                for layer_node in root.findall('.//wms:Layer/wms:Name/..', namespaces=ns):
                    name = layer_node.find('wms:Name', ns).text
                    title = layer_node.find('wms:Title', ns).text
                    if name and title: layers_found.append({'name': name, 'title': title})
            else: # wfs
                ns = {'wfs': 'http://www.opengis.net/wfs'}
                for feature_type in root.findall('.//wfs:FeatureType', namespaces=ns):
                    name = feature_type.find('wfs:Name', ns).text
                    title = feature_type.find('wfs:Title', ns).text
                    if name and title: layers_found.append({'name': name, 'title': title})

            self.distribution_layers_cache = sorted(layers_found, key=lambda x: x['title'])
            
            display_list = []
            for layer in self.distribution_layers_cache:
                display_text = f"{layer.get('title')} ({layer.get('name')})"
                display_list.append(display_text)
                self.layer_data_map[display_text] = layer

            self.completer_model.setStringList(display_list)
            
            self.ui.lineEdit_layer_search.setEnabled(True)
            self.ui.lineEdit_layer_search.clear()
            self.ui.lineEdit_layer_search.setFocus()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Falha ao carregar camadas do GeoServer: {e}")
            self.ui.lineEdit_layer_search.setText("Falha ao carregar")

    def _filter_layer_list(self, filter_text, show_popup=True):
        """Filtra a lista do QCompleter - método opcional se o Qt Completer for suficiente. (Deixado para compatibilidade)"""
        pass

    def _on_layer_selected(self, selected_text):
        if selected_text in self.layer_data_map:
            self.selected_layer_data = self.layer_data_map[selected_text]
        else:
            self.selected_layer_data = None            

    def _add_service_selection(self):
        service_type = self.ui.comboBox_service_type.currentData()
        selected_layer = self.selected_layer_data 

        if not service_type or not selected_layer:
            QtWidgets.QMessageBox.warning(self, "Aviso", "Selecione uma camada na lista.")
            return

        geoserver_url = config_loader.get_geoserver_url()
        service_data = {
            'geoserver_base_url': geoserver_url,
            'geoserver_layer_name': selected_layer.get('name'),
            'geoserver_layer_title': selected_layer.get('title'),
            'online_protocol': service_type.upper()
        }

        if service_type == "wms":
            self.distribution_data['wms_data'] = service_data
        elif service_type == "wfs":
            self.distribution_data['wfs_data'] = service_data
        
        self.update_distribution_display()
        
        # Reset UI
        self.ui.comboBox_service_type.setCurrentIndex(0)
        self.ui.lineEdit_layer_search.clear()
        self.ui.lineEdit_layer_search.setEnabled(False)
        self.iface.messageBar().pushMessage("Sucesso", f"Recurso {service_type.upper()} associado.", level=Qgis.Success)

    # --- INTEGRAÇÃO DA SELEÇÃO DE CONTATOS (HIBRIDA) ---
    def _setup_contact_search(self):
        """Prepara os widgets e lógica da aba Ponto de Contato."""
        # Autocomplete de contatos (igual ao de camadas)
        self.contact_completer_model = QtCore.QStringListModel()
        self.contact_completer = QtWidgets.QCompleter(self.contact_completer_model, self)
        self.contact_completer.setFilterMode(Qt.MatchContains)
        self.contact_completer.setCaseSensitivity(Qt.CaseInsensitive)
        
        completer_style = """
            QAbstractItemView#ContactCompleterPopup {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                outline: none;
            }
        """
        contact_popup = self.contact_completer.popup()
        contact_popup.setObjectName("ContactCompleterPopup")
        contact_popup.setMouseTracking(True)
        contact_popup.setStyleSheet(completer_style)
        
        # Reutilizando o Delegate global
        self._delegate2 = CustomHeightDelegate(contact_popup, height=30, font_size=9)
        contact_popup.setItemDelegate(self._delegate2)
            
        self.ui.lineEdit_contact_search.setCompleter(self.contact_completer)

        self.contact_debounce_timer = QTimer(self)
        self.contact_debounce_timer.setSingleShot(True)
        self.contact_debounce_timer.timeout.connect(self._fetch_contacts_online)

        self.ui.lineEdit_contact_search.textEdited.connect(self._on_contact_search_edited)
        self.contact_completer.activated.connect(self._on_contact_selected)
        
        self.ui.btn_contact_add.clicked.connect(self._add_contact_action)
        
        self.contacts_cache_map = {}
        self.selected_contact_data = None

    def _on_contact_search_edited(self, text):
        if self.plugin.api_session:
            self.contacts_cache_map.clear()
            self.contact_completer_model.setStringList([])
            if len(text) >= 2:
                self.contact_debounce_timer.start(800)
        else:
            self._update_offline_contacts(text)
            
    def _update_offline_contacts(self, filter_text):
        display_list = []
        lower_filt = filter_text.lower()
        
        for key, data in self.form_manager.contatos_predefinidos.items():
            if key == 'nenhum': continue
            org = data.get('contact_organisationName', '')
            sigla = data.get('contact_individualName', '')
            email = data.get('contact_email', '')
            
            if not lower_filt or lower_filt in org.lower() or lower_filt in sigla.lower() or lower_filt in email.lower():
                display_str = f"{sigla} - {org} - {email}" if sigla else f"{org} - {email}"
                display_list.append(display_str)
                self.contacts_cache_map[display_str] = data
                
        self.contact_completer_model.setStringList(display_list)

    def _fetch_contacts_online(self):
        filter_text = self.ui.lineEdit_contact_search.text()
        if not filter_text: return
        
        try:
            gn_urls = config_loader.get_geonetwork_url()
            base_url = gn_urls.get('records_url') 
            if not base_url: return
            
            # GeoNetwork 4.x usa o endpoint /search/records/_search do ES
            es_url = base_url.replace('/records', '/search/records/_search')
            payload = {"size": 100, "query": {"term": {"isTemplate": "s"}}}
            
            response = self.plugin.api_session.post(es_url, json=payload, timeout=5, headers={'Accept': 'application/json'}, verify=False)
            if response.status_code == 200:
                hits = response.json().get('hits', {}).get('hits', [])
                
                current_list = []
                lower_filt = filter_text.lower()
                
                for hit in hits:
                    import re
                    src = hit.get('_source', {})
                    title = src.get('resourceTitleObject', {}).get('default', '')
                    
                    # Extrai sigla dos parênteses se existir
                    sigla_match = re.search(r'\((.*?)\)', title)
                    sigla = sigla_match.group(1).strip() if sigla_match else ''
                    
                    # Se 'Org' não vier, usa o title sem a sigla
                    if 'Org' in src and src['Org']:
                        org = src['Org'].strip()
                    else:
                        org = title.replace(f" ({sigla})", "").strip() if sigla else title.strip()
                        
                    email = src.get('email', '').strip()
                    
                    if lower_filt in org.lower() or lower_filt in email.lower() or lower_filt in sigla.lower():
                        display_str = f"{sigla} - {org} - {email}" if sigla else f"{org} - {email}"
                        if display_str not in current_list:
                            current_list.append(display_str)
                            
                            # Tenta herdar metadados ricos (como role e Endereço) do offline map (usando email como hook)
                            fallback_data = None
                            for key, preset in self.form_manager.contatos_predefinidos.items():
                                if key != 'nenhum' and preset.get('contact_email') == email:
                                    fallback_data = preset
                                    break
                                    
                            if fallback_data:
                                rich_data = fallback_data.copy()
                                rich_data['contact_organisationName'] = org
                                rich_data['contact_individualName'] = sigla or rich_data.get('contact_individualName', '')
                                rich_data['is_geonetwork'] = True
                                rich_data['uuid'] = src.get('uuid')
                                self.contacts_cache_map[display_str] = rich_data
                            else:
                                self.contacts_cache_map[display_str] = {
                                    'is_geonetwork': True,
                                    'uuid': src.get('uuid'),
                                    'contact_organisationName': org,
                                    'contact_individualName': sigla,
                                    'contact_email': email,
                                    'contact_role': 'pointOfContact' 
                                }
                                
                self.contact_completer_model.setStringList(current_list)
                # Força a atualização e expansão do popup do Completer após atualização assíncrona
                self.contact_completer.complete()
        except Exception:
            pass
            
    def _on_contact_selected(self, selected_text):
        if selected_text in self.contacts_cache_map:
            self.selected_contact_data = self.contacts_cache_map[selected_text]
        else:
            self.selected_contact_data = None
            
    def _add_contact_action(self):
        if not self.selected_contact_data:
            QtWidgets.QMessageBox.warning(self, "Aviso", "Selecione um contato da lista primeiro.")
            return

        c_data = self.selected_contact_data.copy()

        # Intercepta se veio do GeoNetwork e puxa o XML real para capturar Regra exata e Nome
        if c_data.get('is_geonetwork') and c_data.get('uuid'):
            try:
                gn_urls = config_loader.get_geonetwork_url()
                base_url = gn_urls.get('records_url')
                if base_url:
                    xml_url = f"{base_url}/{c_data['uuid']}/formatters/xml"
                    response = self.plugin.api_session.get(xml_url, timeout=5, verify=False)
                    if response.status_code == 200:
                        xml_text = response.text
                        import re
                        
                        role_match = re.search(r'CI_RoleCode[^>]*codeListValue="([^"]+)"', xml_text)
                        if role_match:
                            c_data['contact_role'] = role_match.group(1)
                            
                        name_match = re.search(r'<gmd:individualName>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>', xml_text, re.DOTALL)
                        if name_match:
                            c_data['contact_individualName'] = name_match.group(1).strip()
                            
                        org_match = re.search(r'<gmd:organisationName>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>', xml_text, re.DOTALL)
                        if org_match:
                            c_data['contact_organisationName'] = org_match.group(1).strip()
            except Exception:
                pass

        org_text = self.ui._primary_row.field_org.text().strip()
        name_text = self.ui._primary_row.field_name.text().strip()

        if not org_text and not name_text:
            self.form_manager.populate_primary_contact(c_data)
            self.iface.messageBar().pushMessage("Sucesso", "Contato primário definido.", level=Qgis.Success)
        else:
            org = c_data.get('contact_organisationName', '')
            name = c_data.get('contact_individualName', '')
            email = c_data.get('contact_email', '')
            role = c_data.get('contact_role', 'pointOfContact')
            
            row = self.ui._add_contact_row()
            row.field_org.setText(org)
            row.field_name.setText(name)
            row.field_email.setText(email)
            
            index = row.field_role.findData(role)
            if index != -1: row.field_role.setCurrentIndex(index)
            self.iface.messageBar().pushMessage("Sucesso", "Contato anexado à lista.", level=Qgis.Success)

        # Limpa após adicionar
        self.ui.lineEdit_contact_search.clear()
        self.selected_contact_data = None


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

    def closeEvent(self, event):
        """Executado quando o usuário tenta fechar a janela."""
        if self.form_manager.get_is_dirty():
            from qgis.PyQt import QtWidgets
            reply = QtWidgets.QMessageBox.question(self, 
                                        'Alterações não Salvas',
                                        "Você tem alterações que não foram salvas.\nDeseja realmente sair?",
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

    def show_message(self, title, text, icon=None):
        from qgis.PyQt import QtWidgets
        from qgis.PyQt.QtCore import Qt
        if icon is None:
            icon = QtWidgets.QMessageBox.Information
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(icon)
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(text)
        msg_box.setWindowTitle(title)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg_box.exec_()

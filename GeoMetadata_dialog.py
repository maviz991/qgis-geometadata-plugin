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
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
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
from .core.geonetwork_service import GeoNetworkService
from .core.persistence_service import PersistenceService
from . import resources
from .core.plugin_config import config_loader
from .ui.styles import get_stylesheet

# WebEngine imports (Robust detection)
try:
    from qgis.PyQt.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
    from qgis.PyQt.QtWebChannel import QWebChannel
except ImportError:
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
        from PyQt5.QtWebChannel import QWebChannel
    except ImportError:
        QWebEngineView = None
        QWebEnginePage = None
        QWebChannel = None

from .ui.main_bridge import MainBridge
from .ui.geonetwork_bridge import GeoNetworkBridge
from .ui.geoserver_bridge import GeoServerBridge


if QWebEnginePage is not None:
    class _ExternalLinkPage(QWebEnginePage):
        """QWebEnginePage que abre links http(s) clicados no navegador padrão do
        sistema em vez de navegar para longe da UI do plugin dentro do QGIS.
        Navegação interna (file://, usada pelo SPA da própria UI) segue normal."""
        def acceptNavigationRequest(self, url, nav_type, isMainFrame):
            if nav_type == QWebEnginePage.NavigationTypeLinkClicked and url.scheme() in ('http', 'https'):
                QDesktopServices.openUrl(url)
                return False
            return super().acceptNavigationRequest(url, nav_type, isMainFrame)

        def createWindow(self, _type):
            """Links com target="_blank" (ou window.open()) não passam por
            acceptNavigationRequest - o Qt chama createWindow() em vez disso.
            Devolvemos uma página descartável só pra capturar a URL de destino
            assim que ela for definida, abrir no navegador do sistema e jogar fora."""
            throwaway = QWebEnginePage(self.profile(), self)

            def _on_url_ready(url):
                throwaway.urlChanged.disconnect(_on_url_ready)
                QDesktopServices.openUrl(url)
                throwaway.deleteLater()

            throwaway.urlChanged.connect(_on_url_ready)
            return throwaway


# --- 4. Helpers de Estilo ---
class CustomHeightDelegate(QStyledItemDelegate):
    """Delegate para QCompleter popups: altura fixa, hover com borda e seleção com acento."""

    def __init__(self, parent=None, height=30, font_size=9):
        super().__init__(parent)
        self.forced_height = height
        self.forced_font_size = font_size

    def sizeHint(self, option, index):
        """Retorna o tamanho do item com altura forçada."""
        size = super().sizeHint(option, index)
        size.setHeight(self.forced_height)
        return size

    def paint(self, painter, option, index):
        """Pinta fundo (hover/seleção/neutro) e texto do item."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 1. Fundo (Hover ou Seleção)
        is_selected = option.state & QStyle.State_Selected
        is_hovered  = option.state & QStyle.State_MouseOver
        
        if is_selected:
            painter.fillRect(option.rect, QColor("#fef2f2"))
        elif is_hovered:
            painter.fillRect(option.rect, QColor("#bdbdbd"))
            painter.fillRect(option.rect.adjusted(1, 1, -1, -1), QColor("#f5f5f5"))
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
    Botão de navegação do header - hover e estado ativo via setStyleSheet()
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
        # Expande verticalmente para preencher o header - border-bottom alinha ao fundo
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    # ------------------------------------------------------------------
    def _is_dark(self):
        """Retorna True se o tema ativo da janela for escuro."""
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
        """Atualiza estado hover e redesenha o botão."""
        self._hovered = bool(value)
        self._update_style()

    def set_nav_active(self, value):
        """Marca/desmarca este botão como destino ativo de navegação."""
        self._nav_active = bool(value)
        self._update_style()

    # ------------------------------------------------------------------
    def set_nav_menu(self, menu):
        """Vincula um QMenu ao botão e instala o filtro de eventos para manter o hover coeso."""
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
        """Ativa hover e abre o menu ao entrar no botão."""
        self._timer.stop()
        self._apply_hover(True)
        if self._nav_menu and self.isEnabled():
            self._switch_to_me()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Remove hover e inicia temporizador de fechamento ao sair do botão."""
        self._timer.start()
        self._apply_hover(False)
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    def _maybe_close(self):
        """Fecha o menu após o timer expirar se o cursor não estiver sobre ele ou outro NavButton."""
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
        """Mantém o menu aberto enquanto o cursor transita entre botão e menu; troca de menu ao entrar em outro NavButton."""
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
        """Inicializa o diálogo: detecta tema, constrói UI, conecta serviços e aplica estilos."""
        super(GeoMetadataDialog, self).__init__(parent)
        
        # --- Atributos da Classe ---
        self.iface = iface
        self.plugin = plugin_instance
        self.distribution_data = {}
        self.auth_cfg_id = None
        self.current_metadata_uuid = None
        self.form_is_dirty = False
        self._load_contacts()

        # Corrige em background, sem UI, um lxml 5.2.1 bugado (crash nativo
        # conhecido ao gerar XML - ver env_checker.silently_fix_lxml_if_needed).
        from .core.env_checker import silently_fix_lxml_if_needed
        silently_fix_lxml_if_needed()

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
        
        # --- Inicialização dos Microsserviços ---
        from .core.geonetwork_service import GeoNetworkService
        from .core.geoserver_service import GeoServerService
        from .core.persistence_service import PersistenceService
        self.geonetwork_service = GeoNetworkService(self.plugin)
        self.geoserver_service = GeoServerService(self.plugin)
        self.persistence_service = PersistenceService(self.iface)
        # O FormManager será inicializado sob demanda ou vinculado à bridge
        self.ui = None # Será atualizado quando o editor HTML carregar

        self._setup_connections_and_logic()

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
        
    def _load_contacts(self):
        """Lê o arquivo contacts.json e carrega os dados em self.contatos_predefinidos."""
        self.contatos_predefinidos = {}
        try:
            import os, json
            contacts_path = os.path.join(os.path.dirname(__file__), 'assets', 'contacts.json')
            with open(contacts_path, 'r', encoding='utf-8') as f:
                self.contatos_predefinidos = json.load(f)
        except Exception as e:
            self.show_toast("Aviso", f"[SYS-002] Erro ao carregar contatos: {e}", 'warning')

    # --- Métodos de Construção e Configuração da UI (Estrutura) ---
    def _setup_main_window(self):
        """Configura as propriedades da janela principal."""
        self.setWindowIcon(QIcon(":/plugins/geometadata/icon.png"))
        self.setObjectName("GeoMetadataDialog")
        self.setWindowTitle("Geohab Plugin")
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        self.setMinimumSize(860, 520)
        self.resize(1200, 690)

    def _build_ui_structure(self):
        """Cria o QWebEngineView que carregará toda a interface HTML."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.web_view = QWebEngineView()
        self.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if QWebEnginePage is not None:
            self.web_view.setPage(_ExternalLinkPage(self.web_view))
        # Fundo da página (mesma cor de --bg em styles.css, claro ou escuro conforme o tema
        # já detectado em __init__) em vez do branco padrão do QWebEnginePage - sem isso, o
        # instante entre a QWebEngineView aparecer e o primeiro paint do HTML (main.html +
        # CSS ainda carregando) mostrava um "flash" branco puro antes do overlay de
        # carregamento (mesmo --bg) aparecer - no tema escuro, esse flash era pior ainda
        # (branco puro sobre o resto já escuro da janela).
        is_dark = self.property("theme") == "dark"
        self.web_view.page().setBackgroundColor(QColor("#10131a" if is_dark else "#f8fafc"))

        # Configura o QWebChannel para comunicação - três bridges por domínio
        # (genérico, GeoNetwork, GeoServer), cada um exposto ao JS com seu próprio nome.
        self.bridge = MainBridge(self)
        self.gn_bridge = GeoNetworkBridge(self)
        self.gs_bridge = GeoServerBridge(self)
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("bridge", self.bridge)
        self.channel.registerObject("gnBridge", self.gn_bridge)
        self.channel.registerObject("gsBridge", self.gs_bridge)
        self.web_view.page().setWebChannel(self.channel)

        # Carrega o arquivo HTML principal - via setHtml() (não load()) pra poder injetar
        # data-theme="dark"/"light" na tag <html> ANTES do primeiro parse/paint. Fazer essa
        # troca depois, via JS a partir de bridge.get_initial_data() (round-trip Python↔JS
        # assíncrono), pintaria a tela inteira no tema claro primeiro e só depois viraria
        # escura - um flash visível toda vez que o plugin abre com o QGIS em tema escuro.
        template_path = os.path.join(os.path.dirname(__file__), "ui", "templates", "main.html")
        base_url = QUrl.fromLocalFile(template_path)
        with open(template_path, "r", encoding="utf-8") as f:
            html = f.read()
        html = html.replace(
            '<html lang="pt-BR">',
            '<html lang="pt-BR" data-theme="{}">'.format("dark" if is_dark else "light"),
            1
        )
        self.web_view.setHtml(html, base_url)

        # QStackedWidget em vez de adicionar o web_view direto: permite trocar o
        # conteúdo da MESMA janela (ex: login SSO embutido) sem abrir popup separado.
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.web_view)
        layout.addWidget(self.content_stack)

    def _setup_connections_and_logic(self):
        """Conecta os sinais lógicos e inicializa o status."""
        self.update_ui_for_login_status()
        # auto_fill_from_layer e outros serão reativados na Etapa 3 (Editor HTML)

    def on_metadata_changed(self):
        """Callback disparado quando qualquer campo do formulário é editado (dirty flag)."""
        pass

    def closeEvent(self, event):
        """Para todas as QThreads em voo antes de destruir o diálogo.

        Sem isso, qualquer worker ainda em execução (request HTTP, psycopg2, pip) é
        destruído enquanto ainda roda — o Qt chama std::terminate(), que fecha o QGIS
        silenciosamente sem crash dump. Ocorria especialmente ao usar o Plugin Reloader
        ou ao recarregar o plugin enquanto o painel GeoServer estava aberto.

        Padrão: quit() sinaliza encerramento ao event loop da thread; wait(2000) espera
        até 2 s e depois abandona (não bloqueia o QGIS indefinidamente em casos extremos
        como um timeout de 10 s no requests ainda em andamento — o processo Qt já vai
        encerrar de qualquer forma, e 2 s é suficiente para a maioria dos workers).
        """
        # --- Bridges GeoServer (múltiplas listas de workers) ---
        gs_bridge = getattr(self, 'gs_bridge', None)
        if gs_bridge:
            for w in list(getattr(gs_bridge, '_sync_check_workers', [])):
                if w and w.isRunning():
                    w.quit()
                    w.wait(2000)
            for w in list(getattr(gs_bridge, '_layer_info_workers', [])):
                if w and w.isRunning():
                    w.quit()
                    w.wait(2000)
            for attr in (
                '_workspaces_worker', '_datastores_worker', '_featuretypes_worker',
                '_find_datastore_worker', '_publish_worker', '_styles_worker',
                '_apply_style_worker', '_gs_rest_worker', '_pull_layer_worker',
            ):
                w = getattr(gs_bridge, attr, None)
                if w and w.isRunning():
                    w.quit()
                    w.wait(2000)

        # --- Bridges GeoNetwork ---
        gn_bridge = getattr(self, 'gn_bridge', None)
        if gn_bridge:
            for attr in ('_push_worker', '_fetch_worker', '_sync_worker'):
                w = getattr(gn_bridge, attr, None)
                if w and w.isRunning():
                    w.quit()
                    w.wait(2000)

        # --- GatewaySSOWidget (login SSO embutido no content_stack) ---
        stack = getattr(self, 'content_stack', None)
        if stack:
            for i in range(stack.count()):
                widget = stack.widget(i)
                if hasattr(widget, '_verify_worker'):
                    vw = widget._verify_worker
                    if vw and vw.isRunning():
                        widget._done = True   # cancela retries pendentes
                        vw.quit()
                        vw.wait(2000)

        super().closeEvent(event)


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
        header_widget.setFixedHeight(64)
        layout = QHBoxLayout(header_widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 16, 0)

        # Logo clicável - navega para Home
        pixmap = QPixmap(":/plugins/geometadata/img/header_logo.png")
        scaled = pixmap.scaled(170, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
        self._action_gs_fase2 = QAction("Em desenvolvimento  -  Fase 2", self)
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
        """Ativa o indicador visual no botão de navegação correspondente; passa None para desativar todos."""
        for btn in (self._btn_geonetwork, self._btn_geoserver):
            btn.set_nav_active(btn is active_btn)

    def _navigate_to_home(self):
        """Navega para a Home (índice 0)."""
        self._stacked.setCurrentIndex(0)
        self._set_active_nav_btn(None)  # logo é Home - nenhum botão nav ativo

    def _navigate_to_geonetwork(self):
        """Navega para o painel GeoNetwork (índice 1)."""
        self._stacked.setCurrentIndex(1)
        self._set_active_nav_btn(self._btn_geonetwork)

    def _navigate_to_geoserver(self):
        """Os métodos de navegação antigos foram substituídos pela lógica no app.js e main_bridge.py
        Navega para o painel GeoServer (índice 2)."""
        self._stacked.setCurrentIndex(2)
        self._set_active_nav_btn(self._btn_geoserver)

    def _setup_button_connections(self):
        """Conecta ações lógicas (não visuais)."""
        # Ações de menu agora são disparadas via Bridge (JS -> Python)
        pass

    def _setup_login_icons(self):
        """Carrega os ícones de login a partir dos recursos."""
        self.icon_login_ok = QIcon(":/plugins/geometadata/img/login_ok.png")
        self.icon_login_error = QIcon(":/plugins/geometadata/img/login_error.png")
        self.header_btn_login.setIconSize(QSize(20, 20))

    def authenticate(self):
        """Gerencia o ciclo de login/logout.
        
        Abre o diálogo unificado que oferece login via Entra ID (Corporativo) 
        ou Basic Auth (Administrador).
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

        # --- LOGIN UNIFICADO ---
        # 1. Verifica dependências (msal)
        from .core.env_checker import check_and_run_setup
        if not check_and_run_setup(parent=self):
            return

        from .ui.login_dialog import LoginDialog

        entra_cfg = config_loader.get_entra_id_config()
        geoserver_url = config_loader.get_geoserver_url()

        login_dialog = LoginDialog(
            client_id=entra_cfg.get("client_id", ""),
            tenant_id=entra_cfg.get("tenant_id", ""),
            scopes=entra_cfg.get("scopes", ["User.Read"]),
            geoserver_url=geoserver_url,
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
                f"<p style='font-size: 15px; font-weight: bold;'>Autenticação concluída!</p>"
                f"<p><b>Usuário:</b> {self.plugin.auth_username}</p>"
                f"<p style='color: rgba(0,0,0,0.5);'>Você pode Associar camadas e Exportar para Geohab</p>"
                f"<p>Por favor, feche a aba aberta no navegador!</p>"
                f"<p style='font-size: 11px;'>⚠️ <b>Para sua segurança:</b> Não compartilhe conteúdos, barra de endereços ou faça capturas de tela da aba aberta no navegador.</p>"
            )

        self.update_ui_for_login_status()

    def update_ui_for_login_status(self):
        """Notifica a ponte web sobre o status de autenticação."""
        is_logged_in = self.plugin.api_session is not None
        username = self.plugin.auth_username or "Visitante"
        
        # Notifica o JavaScript para atualizar a UI (badge, botões, etc)
        if hasattr(self, 'bridge'):
            self.bridge.auth_status.emit(is_logged_in, username)

    def _normalize_dates(self, metadata_dict):
        """Converte datetime-local do HTML (YYYY-MM-DDTHH:MM) para ISO com Z."""
        for key in ('dateStamp', 'date_creation'):
            val = metadata_dict.get(key, '')
            if val and 'T' in val and not val.endswith('Z'):
                if len(val) == 16:
                    metadata_dict[key] = val + ':00Z'
        return metadata_dict

    def exportar_to_xml(self, metadata_dict=None):
        """Gera o XML e permite salvar no disco manual."""
        if metadata_dict is None:
            if not hasattr(self, 'form_manager') or not self.form_manager:
                self.show_toast('Atenção', '[UI-005] Preencha o formulário em "Catálogo Geohab > Editar Metadados" antes de exportar.', 'warning')
                return
            if not self.form_manager.validate_form(): return
            metadata_dict = self.form_manager.collect_data()

        metadata_dict = self._normalize_dates(metadata_dict)
        try:
            from .core import xml_generator
            cdhu_data = self.contatos_predefinidos.get('cdhu', {})
            xml_payload = xml_generator.generate_xml(metadata_dict, cdhu_data)

            safe_filename = metadata_dict.get('title', 'metadados').replace(' ', '_') + '.xml'
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Salvar Metadados XML', safe_filename, 'Arquivos XML (*.xml)')
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(xml_payload)
                self.iface.messageBar().pushMessage('Sucesso', f'Metadados salvos em: {file_path}', level=Qgis.Success, duration=5)
                js_path = json.dumps(file_path)
                self.show_toast(
                    'Sucesso',
                    f'Metadados salvos em:<br>{file_path}'
                    f"<br><span onclick='bridge.open_file_location({js_path})' "
                    f'style="color:var(--accent);font-weight:600;text-decoration:underline;cursor:pointer;">Abrir pasta</span>',
                    'success'
                )
        except Exception as e:
            self.show_toast('Erro', f'[SYS-003] Falha ao exportar XML: {e}', 'error')

    def exportar_to_geo(self, metadata_dict=None):
        """Exporta para o GeoNetwork usando o GeoNetworkService. A escolha de processamento
        de UUID (Nenhum/Sobrescrever/Gerar novo) é feita no modal HTML antes da chamada
        e chega aqui em metadata_dict['uuidProcessing']."""
        if metadata_dict is None:
            if not hasattr(self, 'form_manager') or not self.form_manager:
                self.show_toast('Atenção', '[UI-006] Preencha o formulário em "Catálogo Geohab > Editar Metadados" antes de publicar.', 'warning')
                return
            if not self.form_manager.validate_form(): return
            metadata_dict = self.form_manager.collect_data()

        if not self.plugin.api_session:
            self.show_toast('Não Autenticado', '[UI-007] Conecte ao Geohab primeiro.', 'warning')
            return

        metadata_dict = self._normalize_dates(metadata_dict)
        uuid_processing = metadata_dict.pop('uuidProcessing', None) or 'NOTHING'

        try:
            from .core import xml_generator
            cdhu_data = self.contatos_predefinidos.get('cdhu', {})
            xml_payload = xml_generator.generate_xml(metadata_dict, cdhu_data)
        except Exception as e:
            self.show_toast('Erro', f'[SYS-004] Falha ao gerar XML: {e}', 'error')
            return

        # As duas chamadas de rede (publicar + buscar dateStamp de volta) rodam numa
        # QThread - se rodassem direto aqui, travariam a UI inteira do QGIS (inclusive o
        # próprio indicador de "Publicando..." no JS) até o servidor do Geohab responder.
        from .core.plugin_config import config_loader
        from .ui.geonetwork_workers import _GnPublishWorker
        self._gn_publish_worker = _GnPublishWorker(self.geonetwork_service, xml_payload, config_loader, uuid_processing)
        self._gn_publish_worker.done.connect(
            lambda uuid_criado, date_stamp, error: self._on_gn_publish_done(metadata_dict, uuid_criado, date_stamp, error)
        )
        self._gn_publish_worker.start()

    def _on_gn_publish_done(self, metadata_dict, uuid_criado, date_stamp, error):
        """Callback (thread principal) quando o _GnPublishWorker termina a publicação no GN."""
        from .core.plugin_config import config_loader
        if error or not uuid_criado:
            self.show_toast('Erro', f'Falha no GeoNetwork: {error or "resposta inesperada do servidor"}', 'error')
            return
        metadata_dict['metadata_uuid'] = uuid_criado
        # dateStamp real que o GN carimbou ao processar (não o que estava no formulário
        # antes de publicar) - sem isso, a próxima checagem de sync sempre acha que o GN
        # tem uma "atualização nova", já que o dateStamp local nunca bateria com o do GN.
        if date_stamp:
            metadata_dict['dateStamp'] = date_stamp
        self.save_metadata(metadata_dict=metadata_dict, is_automatic_resave=True)
        if hasattr(self, 'gn_bridge'):
            self.gn_bridge.gn_publish_succeeded.emit(uuid_criado)
        view_url = config_loader.get_metadata_view_url(uuid_criado)
        self.show_toast(
            'Sucesso',
            f'Metadado exportado.<br>UUID: {uuid_criado}'
            f'<br><a href="{view_url}" target="_blank">Acesse aqui</a>',
            'success'
        )

    def save_metadata(self, metadata_dict=None, is_automatic_resave=False):
        """Usa o PersistenceService para salvar no DB ou XML Sidecar."""
        if metadata_dict is None:
            if not hasattr(self, 'form_manager') or not self.form_manager:
                return
            if not is_automatic_resave and not self.form_manager.validate_form(): return
            metadata_dict = self.form_manager.collect_data()

        layer = self.iface.activeLayer()
        cdhu_data = self.contatos_predefinidos.get('cdhu', {})
        success = self.persistence_service.save(layer, metadata_dict, cdhu_data, is_automatic_resave, self)
        # Só avisa o badge num save explícito do usuário ("Continuar Depois") - o resave
        # automático pós-publicação já tem seu próprio aviso (gn_publish_succeeded).
        if success and not is_automatic_resave and hasattr(self, 'gn_bridge'):
            uuid = metadata_dict.get('metadata_uuid') or metadata_dict.get('metadataId') or ''
            self.gn_bridge.local_save_succeeded.emit(uuid)

        # "Continuar Depois" (e o resave automático) também aproveitam pra promover um
        # eventual rascunho de publicação no GeoServer (aba Destino/Identificação, ainda
        # não publicado) pra dentro do banco - silencioso, sem toast próprio, pra não
        # atrapalhar quem só quer salvar o metadado e seguir pro painel GeoServer depois.
        if success and layer:
            self._promote_gs_draft_to_db(layer)

    def _promote_gs_draft_to_db(self, layer):
        """Se existir um rascunho local de publicação no GeoServer (gsBridge.save_draft,
        ver ui/geoserver_bridge.py) pra essa camada, grava ele em geoserver_publish_xml
        (public.qgis_geometadata_plugin) - complementa o rascunho local (por máquina) com
        uma cópia durável no banco, mesmo antes de a camada ser publicada de verdade."""
        if not hasattr(self, 'gs_bridge') or not hasattr(self, 'geoserver_service'):
            return
        try:
            layer_key = layer.source() or layer.id()
            draft = self.gs_bridge._load_all_drafts().get(layer_key)
            if not draft or not draft.get('workspace'):
                return  # nada de útil pra promover ainda
            # Estilo: promove só a ESCOLHA (fonte + nome), como os demais campos - nada é
            # exportado/enviado ao GeoServer aqui (ver GeoServerBridge.derive_style_fields).
            style_source, style_name, style_workspace, style_additional_json = self.gs_bridge.derive_style_fields({
                'source': draft.get('style_source') or '',
                'name': draft.get('style_name') or draft.get('published_name') or '',
                'existing_name': draft.get('style_existing_name') or '',
                'existing_workspace': draft.get('style_existing_workspace') or '',
                'additional': draft.get('style_additional') or []
            }, draft.get('workspace') or '')
            self.geoserver_service.save_publish_destination(
                layer,
                draft.get('workspace') or '',
                draft.get('datastore') or '',
                draft.get('published_name') or '',
                draft.get('title') or '',
                draft.get('abstract') or '',
                draft.get('keywords') or [],
                style_source=style_source, style_name=style_name, style_workspace=style_workspace,
                style_additional_json=style_additional_json
            )
        except Exception as exc:
            print(f"GeoMetadata [_promote_gs_draft_to_db]: {exc}")

    def sanitize_title(self, value):
        """Remove caracteres especiais e normaliza espaços para uso como nome de arquivo."""
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
        if xml_content and hasattr(self, 'form_manager') and self.form_manager:
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
        """Carrega a lista de camadas WMS ou WFS do GeoServer e preenche o QCompleter."""
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
        """Armazena os dados da camada escolhida no completer para uso na associação."""
        if selected_text in self.layer_data_map:
            self.selected_layer_data = self.layer_data_map[selected_text]
        else:
            self.selected_layer_data = None            

    def _add_service_selection(self):
        """Confirma a seleção de camada WMS/WFS e grava em distribution_data."""
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
        """Despacha para busca online (com debounce) ou offline conforme estado de sessão."""
        if self.plugin.api_session:
            self.contacts_cache_map.clear()
            self.contact_completer_model.setStringList([])
            if len(text) >= 2:
                self.contact_debounce_timer.start(800)
        else:
            self._update_offline_contacts(text)
            
    def _update_offline_contacts(self, filter_text):
        """Filtra contatos do arquivo local contacts.json sem requerer sessão ativa."""
        display_list = []
        lower_filt = filter_text.lower()
        
        for key, data in self.contatos_predefinidos.items():
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
        """Busca contatos no GeoNetwork via Elasticsearch e mescla com dados locais enriquecidos."""
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
                            for key, preset in self.contatos_predefinidos.items():
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
        """Armazena o contato escolhido no completer para uso na adição."""
        if selected_text in self.contacts_cache_map:
            self.selected_contact_data = self.contacts_cache_map[selected_text]
        else:
            self.selected_contact_data = None
            
    def _add_contact_action(self):
        """Preenche o contato primário ou adiciona nova linha de contato conforme o estado do formulário."""
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

        if not hasattr(self, 'ui') or not self.ui or not hasattr(self, 'form_manager') or not self.form_manager:
            return

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
        if hasattr(self, 'form_manager') and self.form_manager and self.form_manager.get_is_dirty():
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
        """Exibe um QMessageBox nativo com suporte a Rich Text (HTML). Usado como fallback
        de `show_toast` quando a bridge/webview ainda não está pronta."""
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

    def show_toast(self, title, message, msg_type='info'):
        """Notificação no padrão visual HTML/CSS do projeto (Modal.alert via bridge).
        Cai para o QMessageBox nativo (`show_message`) se a bridge ainda não existir
        (ex.: erros durante a construção do diálogo, antes da webview carregar)."""
        if getattr(self, 'bridge', None):
            self.bridge.toast.emit(message, title, msg_type)
            return
        icon_map = {
            'error': QtWidgets.QMessageBox.Critical,
            'warning': QtWidgets.QMessageBox.Warning,
        }
        self.show_message(title, message, icon=icon_map.get(msg_type, QtWidgets.QMessageBox.Information))

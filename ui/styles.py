# styles.py

def get_stylesheet(img_dir: str) -> str:
    """
    Retorna o QSS completo do plugin.
    img_dir: caminho absoluto para a pasta img/ (forward-slashes).
    """
    img = img_dir.replace("\\", "/")

    # --- Variáveis de cor (alterar aqui muda globalmente) ---
    accent = "#e5222d"          # cor principal (vermelho CDHU)
    accent_hover = "#c0111b"    # hover mais escuro
    accent_light = "#fef2f2"    # fundo leve de destaque

    return f"""
    /* ================================================================
       BASE — Tipografia
       ================================================================ */
    * {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                     Helvetica, Arial, sans-serif;
        font-size: 13px;
    }}

    /* ================================================================
       JANELA PRINCIPAL
       ================================================================ */
    #GeoMetadataDialog {{
        background-color: #f1f5f9;
    }}
    #GeoMetadataDialog[theme="dark"] {{
        background-color: #0f172a;
    }}

    /* ================================================================
       HEADER — barra de navegação estilo web
       ================================================================ */
    #Header {{
        background-color: #ffffff;
        border-bottom: 1px solid #e2e8f0;
        padding: 0 16px;
        min-height: 64px;
    }}
    #GeoMetadataDialog[theme="dark"] #Header {{
        background-color: #1e293b;
        border-bottom: 1px solid #334155;
    }}

    /* Botões de menu dropdown (Arquivo, GeoNetwork, GeoServer) — base */
    #HeaderDropdownButton {{
        background-color: transparent;
        color: #475569;
        font-size: 14px;
        font-weight: 600;
        border: none;
        border-bottom: 3px solid transparent;
        padding: 10px 14px 10px 16px;
        margin: 0 1px;
    }}
    /* Hover e navActive gerenciados por NavButton._update_style() via setStyleSheet() */

    /* Remove artefatos visuais do menu embutido no QPushButton */
    #HeaderDropdownButton::menu-button {{ background: transparent; border: none; width: 0; }}
    #HeaderDropdownButton::menu-arrow  {{ image: none; width: 0; height: 0; }}
    #HeaderDropdownButton::menu-indicator {{ width: 0; image: none; }}

    #GeoMetadataDialog[theme="dark"] #HeaderDropdownButton {{ color: #94a3b8; }}

    /* Logo clicável — navega para Home */
    #LogoButton {{
        background: transparent;
        border: none;
        padding: 0;
        margin: 0 4px 0 0;
    }}
    #LogoButton:hover {{ background: transparent; }}
    #LogoButton:pressed {{ background: transparent; }}

    /* Botão de login */
    #ConnectButton {{
        background-color: black;
        color: white;
        font-weight: 700;
        font-size: 12px;
        border-radius: 8px;
        padding: 6px 16px;
    }}
    #ConnectButton:hover {{ background-color: #363636; }}
    #GeoMetadataDialog[theme="dark"] #ConnectButton {{
        color: #363636;
        border-color: #363636;
    }}
    #GeoMetadataDialog[theme="dark"] #ConnectButton:hover {{
        background-color: rgba(56,189,248,0.1);
    }}

    /* ================================================================
       QMENU — dropdown popover moderno
       ================================================================ */
    #DropdownMenu {{
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 4px 0;
    }}
    #DropdownMenu::item {{
        color: #1e293b;
        font-size: 13px;
        padding: 8px 20px;
        border-radius: 4px;
        margin: 1px 6px;
    }}
    #DropdownMenu::item:selected {{
        background-color: {accent_light};
        color: {accent};
    }}
    /* Item de navegacao principal — negrito, cor accent */
    #DropdownMenu::item[objectName="NavAction"] {{
        font-weight: 700;
        color: #1e293b;
    }}
    #DropdownMenu::item[objectName="NavAction"]:selected {{
        background-color: {accent_light};
        color: {accent};
    }}
    /* Item desabilitado padrao */
    #DropdownMenu::item:disabled {{ color: #94a3b8; font-style: italic; }}
    #DropdownMenu::separator {{
        height: 1px;
        background: #e2e8f0;
        margin: 4px 12px;
    }}
    #GeoMetadataDialog[theme="dark"] #DropdownMenu {{
        background-color: #1e293b;
        border-color: #334155;
    }}
    #GeoMetadataDialog[theme="dark"] #DropdownMenu::item {{ color: #cbd5e1; }}
    #GeoMetadataDialog[theme="dark"] #DropdownMenu::item:selected {{
        background-color: #1e3a5f;
        color: #38bdf8;
    }}
    #GeoMetadataDialog[theme="dark"] #DropdownMenu::item:disabled {{
        color: #475569;
    }}

    /* ================================================================
       CARD — área branca onde o formulário vive
       ================================================================ */
    QWidget[class="Card"] {{
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
    }}
    #GeoMetadataDialog[theme="dark"] QWidget[class="Card"] {{
        background-color: #1e293b;
        border-color: #334155;
    }}

    /* ================================================================
       PAINEL DE DISTRIBUIÇÃO (WMS / WFS)
       ================================================================ */
    QGroupBox#DistributionPanel {{
        background-color: #f8fafc;
        border: none;
        border-bottom: 1px solid #e2e8f0;
        border-radius: 0;
        padding: 8px 16px;
        font-weight: 600;
        color: #64748b;
        font-size: 11px;
    }}
    QGroupBox#DistributionPanel::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 4px;
        color: #94a3b8;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    #wms_badge, #wfs_badge {{
        background-color: #e2e8f0;
        color: #64748b;
        font-weight: 700;
        font-size: 11px;
        padding: 3px 8px;
        border-radius: 10px;
        min-width: 32px;
        max-width: 32px;
    }}
    #wms_badge[active="true"], #wfs_badge[active="true"] {{
        background-color: #10b981;
        color: #ffffff;
    }}
    #LayerNameLabel {{ color: #475569; font-size: 12px; }}
    #ClearButton {{
        background: transparent;
        border: none;
        color: #94a3b8;
        font-size: 11px;
    }}
    #ClearButton:hover {{ color: #ef4444; }}

    #GeoMetadataDialog[theme="dark"] QGroupBox#DistributionPanel {{
        background-color: #1e293b;
        border-bottom-color: #334155;
    }}
    #GeoMetadataDialog[theme="dark"] #wms_badge,
    #GeoMetadataDialog[theme="dark"] #wfs_badge {{
        background-color: #334155;
        color: #94a3b8;
    }}
    #GeoMetadataDialog[theme="dark"] #wms_badge[active="true"],
    #GeoMetadataDialog[theme="dark"] #wfs_badge[active="true"] {{
        background-color: #10b981;
        color: #ffffff;
    }}

    /* ================================================================
       SCROLL AREA E CONTAINER
       ================================================================ */
    #DynamicScrollArea, #FormContainer, #FieldWrapper {{
        background: transparent;
        border: none;
    }}

    /* ================================================================
       SEÇÕES COLAPSÁVEIS
       ================================================================ */
    #CollapsibleSection {{ background: transparent; }}

    #CollapsibleHeader {{
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
        padding: 0 12px;
        text-align: left;
        font-size: 13px;
        font-weight: 600;
        color: #475569;
    }}
    #CollapsibleHeader:hover {{
        background-color: #f1f5f9;
        color: #1e293b;
        border-color: #cbd5e1;
    }}
    #CollapsibleHeader[expanded="true"] {{
        background-color: #f1f5f9;
        border-bottom: none;
        border-radius: 4px 4px 0 0;
    }}

    #SectionTitle {{
        color: #334155;
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.2px;
    }}

    /* Seta nativa Qt do QToolButton — estilizamos a cor */
    #SectionArrow {{
        background: transparent;
        border: none;
        color: #94a3b8;
    }}

    #SectionDivider {{ color: #e2e8f0; max-height: 1px; }}
    #CollapsibleBody {{
        background-color: #f1f5f9;
        border: 1px solid #e2e8f0;
        border-top: none;
        border-radius: 0 0 4px 4px;
        padding: 4px;
    }}

    #GeoMetadataDialog[theme="dark"] #CollapsibleHeader {{
        background-color: #1e293b;
        border-top-color: #334155;
    }}
    #GeoMetadataDialog[theme="dark"] #CollapsibleHeader:hover {{
        background-color: #273549;
    }}
    #GeoMetadataDialog[theme="dark"] #SectionTitle {{ color: #cbd5e1; }}
    #GeoMetadataDialog[theme="dark"] #SectionDivider {{ color: #334155; }}
    #GeoMetadataDialog[theme="dark"] #CollapsibleBody {{ background-color: #1e293b; }}

    /* ================================================================
       LABELS DE CAMPO — estilo GeoNetwork (escuro, acima do input)
       ================================================================ */
    #FieldLabel {{
        color: #1e293b;
        font-size: 12px;
        font-weight: 700;
        padding-bottom: 2px;
    }}
    #GeoMetadataDialog[theme="dark"] #FieldLabel {{ color: #cbd5e1; }}

    /* ================================================================
       INPUTS — estilo GeoNetwork (fundo cinza claro, pill-shaped)
       ================================================================ */
    QLineEdit, QTextEdit, QSpinBox, QDateTimeEdit, QDateEdit, QTimeEdit {{
        background-color: #f5f5f5;
        border: 1.5px solid #e0e0e0;
        border-radius: 2px;
        padding: 5px 10px;
        color: #1e293b;
        font-size: 13px;
        selection-background-color: {accent};
        selection-color: #ffffff;
    }}
    QTextEdit {{
        border-radius: 8px;
        padding: 8px 10px;
    }}
    QLineEdit:hover, QTextEdit:hover, QSpinBox:hover, QDateTimeEdit:hover,
    QDateEdit:hover, QTimeEdit:hover {{
        border-color: #bdbdbd;
    }}
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateTimeEdit:focus,
    QDateEdit:focus, QTimeEdit:focus {{
        border: 2px solid {accent};
        background-color: #ffffff;
        outline: none;
    }}
    QLineEdit:disabled, QTextEdit:disabled, QSpinBox:disabled {{
        background-color: #eeeeee;
        color: #9e9e9e;
        border-color: #e0e0e0;
    }}

    /* SpinBox — setas discretas */
    QSpinBox::up-button, QSpinBox::down-button {{
        width: 22px;
        border: none;
        background: transparent;
        subcontrol-origin: border;
    }}
    QSpinBox::up-button   {{ subcontrol-position: top right; }}
    QSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QSpinBox::up-arrow    {{
        image: url({img}/chevron_down.svg);
        width: 12px; height: 12px;
        /* rotacionado via transform não é suportado no QSS — deixamos como seta padrão */
    }}
    QSpinBox::down-arrow  {{
        image: url({img}/chevron_down.svg);
        width: 12px; height: 12px;
    }}

    /* DateTimeEdit */
    QDateTimeEdit::drop-down {{
        subcontrol-position: center right;
        width: 28px;
        border: none;
        background: transparent;
    }}
    QDateTimeEdit::down-arrow {{
        image: url({img}/chevron_down.svg);
        width: 14px; height: 14px;
    }}

    /* Dark — inputs */
    #GeoMetadataDialog[theme="dark"] QLineEdit,
    #GeoMetadataDialog[theme="dark"] QTextEdit,
    #GeoMetadataDialog[theme="dark"] QSpinBox,
    #GeoMetadataDialog[theme="dark"] QDateTimeEdit {{
        background-color: #0f172a;
        border-color: #334155;
        color: #f1f5f9;
    }}
    #GeoMetadataDialog[theme="dark"] QLineEdit:hover,
    #GeoMetadataDialog[theme="dark"] QTextEdit:hover,
    #GeoMetadataDialog[theme="dark"] QSpinBox:hover,
    #GeoMetadataDialog[theme="dark"] QDateTimeEdit:hover {{
        border-color: #475569;
    }}
    #GeoMetadataDialog[theme="dark"] QLineEdit:focus,
    #GeoMetadataDialog[theme="dark"] QTextEdit:focus,
    #GeoMetadataDialog[theme="dark"] QSpinBox:focus,
    #GeoMetadataDialog[theme="dark"] QDateTimeEdit:focus {{
        border: 2px solid #38bdf8;
        background-color: #0d1929;
    }}

    /* ================================================================
       COMBOBOX — visual moderno com seta SVG
       ================================================================ */
    QComboBox {{
        background-color: #f5f5f5;
        border: 1.5px solid #e0e0e0;
        border-radius: 8px;
        padding: 5px 30px 5px 10px;
        color: #1e293b;
        font-size: 13px;
    }}
    QComboBox:hover {{ border-color: #bdbdbd; }}
    QComboBox:focus {{ border: 2px solid {accent}; padding: 6px 33px 6px 13px; }}
    QComboBox:on    {{ border-color: {accent}; border-radius: 8px; }}
    QComboBox:disabled {{
        background-color: #eeeeee;
        color: #9e9e9e;
        border-color: #e0e0e0;
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 36px;
        border: none;
        background: transparent;
    }}
    QComboBox::down-arrow {{
        image: url({img}/chevron_down.svg);
        width: 14px;
        height: 14px;
    }}

    QComboBox QAbstractItemView {{
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 2px;
        padding: 4px;
        selection-background-color: {accent_light};
        selection-color: {accent};
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 10px 14px;
        border-radius: 2px;
        min-height: 30px;
        color: #1e293b;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: #f5f5f5;
    }}
    QComboBox QAbstractItemView::item:selected {{
        background-color: {accent_light};
        color: {accent};
    }}

    /* Dark — combobox */
    #GeoMetadataDialog[theme="dark"] QComboBox {{
        background-color: #0f172a;
        border-color: #334155;
        color: #f1f5f9;
    }}
    #GeoMetadataDialog[theme="dark"] QComboBox:hover  {{ border-color: #475569; }}
    #GeoMetadataDialog[theme="dark"] QComboBox:focus  {{ border: 2px solid #38bdf8; }}
    #GeoMetadataDialog[theme="dark"] QComboBox::down-arrow {{
        image: url({img}/chevron_down_white.svg);
    }}
    #GeoMetadataDialog[theme="dark"] QComboBox QAbstractItemView {{
        background-color: #1e293b;
        border-color: #334155;
        color: #f1f5f9;
        selection-background-color: #1e3a5f;
        selection-color: #38bdf8;
    }}
    #GeoMetadataDialog[theme="dark"] QComboBox QAbstractItemView::item:hover {{
        background-color: #273549;
    }}

    /* ================================================================
       TABELA DE CONTATOS
       ================================================================ */
    #ContactColHeader {{
        color: #94a3b8;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        padding: 0 4px;
    }}

    #ContactCell {{
        background-color: #f5f5f5;
        border: 1.5px solid #e0e0e0;
        border-radius: 2px;
        padding: 7px 10px;
        font-size: 12px;
        color: #1e293b;
    }}
    #ContactCell:focus  {{ border: 2px solid {accent}; background: #ffffff; }}
    #ContactCell:hover  {{ border-color: #bdbdbd; }}

    #ContactSearch {{
        background-color: #f5f5f5;
        border: 1.5px solid #e0e0e0;
        border-radius: 2px;
        padding: 7px 14px;
        font-size: 12px;
        color: #1e293b;
    }}
    #ContactSearch:focus {{
        border: 2px solid {accent};
        background-color: #ffffff;
    }}

    #SearchButton {{
        background-color: #f1f5f9;
        color: #64748b;
        border: 1.5px solid #e2e8f0;
        border-radius: 8px;
        font-size: 14px;
        padding: 0;
    }}
    #SearchButton:hover {{ background-color: #e2e8f0; }}

    #AddContactButton {{
        background-color: {accent};
        color: #ffffff;
        font-size: 18px;
        font-weight: bold;
        border: none;
        border-radius: 8px;
        padding: 0;
    }}
    #AddContactButton:hover   {{ background-color: {accent_hover}; }}
    #AddContactButton:pressed {{ background-color: {accent_hover}; }}

    #RemoveContactButton {{
        background-color: transparent;
        color: #94a3b8;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        padding: 4px 8px;
    }}
    #RemoveContactButton:hover {{
        color: #ef4444;
        border-color: #fecaca;
        background-color: #fef2f2;
    }}

    /* Dark — tabela de contatos */
    #GeoMetadataDialog[theme="dark"] #ContactCell {{
        background-color: #0f172a;
        border-color: #334155;
        color: #f1f5f9;
    }}
    #GeoMetadataDialog[theme="dark"] #ContactCell:focus {{ border-color: #38bdf8; }}
    #GeoMetadataDialog[theme="dark"] #ContactSearch {{
        background-color: #0f172a;
        border-color: #334155;
        color: #f1f5f9;
    }}
    #GeoMetadataDialog[theme="dark"] #ContactSearch:focus {{ border-color: #38bdf8; }}
    #GeoMetadataDialog[theme="dark"] #SearchButton {{
        background-color: #1e293b;
        border-color: #334155;
        color: #94a3b8;
    }}
    #GeoMetadataDialog[theme="dark"] #RemoveContactButton {{
        border-color: #334155;
        color: #64748b;
    }}

    /* ================================================================
       BOTÕES GERAIS
       ================================================================ */

    /* Botão "Hoje" e afins */
    #TodayButton {{
        background-color: #f1f5f9;
        color: #475569;
        border: 1.5px solid #e2e8f0;
        border-radius: 8px;
        padding: 7px 14px;
        font-size: 12px;
        font-weight: 600;
    }}
    #TodayButton:hover  {{ background-color: #e2e8f0; color: #0f172a; }}
    #TodayButton:pressed {{ background-color: #cbd5e1; }}

    #GeoMetadataDialog[theme="dark"] #TodayButton {{
        background-color: #1e293b;
        border-color: #334155;
        color: #94a3b8;
    }}
    #GeoMetadataDialog[theme="dark"] #TodayButton:hover {{
        background-color: #273549;
        color: #f1f5f9;
    }}

    /* QToolButton genérico (ex.: seta de seção) */
    QToolButton {{
        background: transparent;
        border: none;
        padding: 2px;
    }}

    /* ================================================================
       LABEL DE SUPORTE (rodapé)
       ================================================================ */
    #label_support_link {{
        color: #94a3b8;
        font-size: 11px;
    }}

    /* ================================================================
       ABAS — QTabWidget estilo web
       ================================================================ */
    #FormTabs {{
        background: #f1f5f9;
        border: none;
    }}

    /* Painel de conteúdo das abas */
    #FormTabs QTabWidget::pane {{
        border: none;
        border-top: 2px solid #e2e8f0;
        background-color: transparent;
    }}

    /* Barra de abas */
    #FormTabs QTabBar {{
        background: transparent;
    }}
    #FormTabs QTabBar::tab {{
        background: transparent;
        color: #64748b;
        font-size: 12px;
        font-weight: 600;
        padding: 8px 10px;
        border: none;
        border-bottom: 2px solid transparent;
        margin-right: 0px;
    }}
    #FormTabs QTabBar::tab:hover {{
        color: #6d7075;
        background: #f8fafc;
        border-bottom: 2px solid #cbd5e1;
    }}
    #FormTabs QTabBar::tab:selected {{
        color: #e5222d;
        background: transparent;
        border-bottom: 2px solid #e5222d;
    }}
    #FormTabs QTabBar::tab:disabled {{
        color: #cbd5e1;
        background: gray;
    }}

    /* ================================================================
       SUB-ABAS — dentro de Identificação
       ================================================================ */
    #SubTabs {{
        background: #ffffff;
        border: none;
    }}
    #SubTabs QTabWidget::pane {{
        border: none;
        border-top: 1px solid #e2e8f0;
        background-color: #ffffff;
    }}
    #SubTabs QTabBar {{
        background: #ffffff;
    }}
    #SubTabs QTabBar::tab {{
        background: transparent;
        color: #64748b;
        font-size: 11px;
        font-weight: 600;
        padding: 6px 12px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    #SubTabs QTabBar::tab:hover {{
        color: #334155;
        border-bottom: 2px solid #cbd5e1;
    }}
    #SubTabs QTabBar::tab:selected {{
        color: {accent};
        border-bottom: 2px solid {accent};
    }}

    /* Scroll dentro das abas */
    #TabScrollArea, #TabScrollArea > QWidget > QWidget {{
        background: #ffffff;
        border: none;
    }}
    #TabContent {{
        background: #ffffff;
    }}

    /* Dark — abas */
    #GeoMetadataDialog[theme="dark"] #FormTabs QTabWidget::pane {{
        border-top-color: #334155;
        background-color: #1e293b;
    }}
    #GeoMetadataDialog[theme="dark"] #FormTabs QTabBar::tab {{
        color: #64748b;
    }}
    #GeoMetadataDialog[theme="dark"] #FormTabs QTabBar::tab:hover {{
        color: #94a3b8;
        background: #273549;
        border-bottom-color: #475569;
    }}
    #GeoMetadataDialog[theme="dark"] #FormTabs QTabBar::tab:selected {{
        color: #38bdf8;
        border-bottom-color: #38bdf8;
    }}
    #GeoMetadataDialog[theme="dark"] #TabContent,
    #GeoMetadataDialog[theme="dark"] #TabScrollArea > QWidget > QWidget {{
        background: #1e293b;
    }}

    /* Sub-seção na aba de contato */
    #SubSectionLabel {{
        color: #475569;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.3px;
    }}
    #GeoMetadataDialog[theme="dark"] #SubSectionLabel {{ color: #64748b; }}

    #TableDivider {{ color: #e2e8f0; max-height: 1px; }}
    #GeoMetadataDialog[theme="dark"] #TableDivider {{ color: #334155; }}

    /* Footer bar */
    #FooterBar {{
        background: #f8fafc;
        border-top: 1px solid #e2e8f0;
    }}
    #GeoMetadataDialog[theme="dark"] #FooterBar {{
        background: #1e293b;
        border-top-color: #334155;
    }}

    /* ================================================================
       SCROLLBAR — discreta e moderna
       ================================================================ */
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: #cbd5e1;
        border-radius: 3px;
        min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{ background: #94a3b8; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

    #GeoMetadataDialog[theme="dark"] QScrollBar::handle:vertical {{ background: #334155; }}
    #GeoMetadataDialog[theme="dark"] QScrollBar::handle:vertical:hover {{ background: #475569; }}

    /* ================================================================
       GEOSERVER PANEL — placeholder Fase 2
       ================================================================ */
    #GeoServerPanel {{
        background-color: #f1f5f9;
    }}
    #GeoMetadataDialog[theme="dark"] #GeoServerPanel {{
        background-color: #0f172a;
    }}

    #GeoServerPlaceholderCard {{
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
    }}
    #GeoMetadataDialog[theme="dark"] #GeoServerPlaceholderCard {{
        background-color: #1e293b;
        border-color: #334155;
    }}

    #GeoServerPlaceholderTitle {{
        font-size: 18px;
        font-weight: 700;
        color: #1e293b;
    }}
    #GeoMetadataDialog[theme="dark"] #GeoServerPlaceholderTitle {{
        color: #f1f5f9;
    }}

    #GeoServerPlaceholderDesc {{
        font-size: 13px;
        color: #64748b;
        line-height: 1.6;
    }}
    #GeoMetadataDialog[theme="dark"] #GeoServerPlaceholderDesc {{
        color: #94a3b8;
    }}

    #PlaceholderSeparator {{
        color: #e2e8f0;
        max-height: 1px;
    }}
    #GeoMetadataDialog[theme="dark"] #PlaceholderSeparator {{
        color: #334155;
    }}

    #GeoServerIconLabel {{
        font-size: 48px;
    }}

    #FeatureEmoji {{
        font-size: 16px;
    }}

    #FeatureText {{
        font-size: 13px;
        color: #475569;
    }}
    #GeoMetadataDialog[theme="dark"] #FeatureText {{
        color: #94a3b8;
    }}

    #ComingSoonBadge {{
        background-color: #fef3c7;
        color: #92400e;
        border: 1px solid #fde68a;
        border-radius: 20px;
        padding: 6px 20px;
        font-size: 12px;
        font-weight: 700;
    }}
    #GeoMetadataDialog[theme="dark"] #ComingSoonBadge {{
        background-color: #1c1917;
        color: #fbbf24;
        border-color: #78350f;
    }}

    /* ================================================================
       HOME PANEL — tela inicial com cards de módulos
       ================================================================ */
    #HomePanel {{
        background-color: #f1f5f9;
    }}
    #GeoMetadataDialog[theme="dark"] #HomePanel {{
        background-color: #0f172a;
    }}

    #HomeTitleBar {{ background: transparent; }}

    #HomeTitle {{
        font-size: 22px;
        font-weight: 800;
        color: #0f172a;
        letter-spacing: -0.3px;
    }}
    #GeoMetadataDialog[theme="dark"] #HomeTitle {{ color: #f1f5f9; }}

    #HomeSubtitle {{
        font-size: 13px;
        color: #64748b;
        line-height: 1.6;
    }}
    #GeoMetadataDialog[theme="dark"] #HomeSubtitle {{ color: #94a3b8; }}

    #HomeCardsContainer {{ background: transparent; }}

    /* Card base */
    #HomeCard_active, #HomeCard_soon {{
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
    }}
    #HomeCard_active:hover {{
        border-color: {accent};
        background-color: #fefefe;
    }}
    #HomeCard_soon {{
        background-color: #fafafa;
        border-color: #e2e8f0;
        opacity: 0.85;
    }}
    #GeoMetadataDialog[theme="dark"] #HomeCard_active,
    #GeoMetadataDialog[theme="dark"] #HomeCard_soon {{
        background-color: #1e293b;
        border-color: #334155;
    }}
    #GeoMetadataDialog[theme="dark"] #HomeCard_active:hover {{
        border-color: {accent};
    }}

    /* Ícone do card */
    #CardIcon {{
        font-size: 36px;
    }}

    /* Título do card */
    #CardTitle {{
        font-size: 17px;
        font-weight: 800;
        color: #0f172a;
        letter-spacing: -0.2px;
    }}
    #GeoMetadataDialog[theme="dark"] #CardTitle {{ color: #f1f5f9; }}

    /* Subtítulo (badge de status) */
    #CardSubtitle {{
        font-size: 11px;
        font-weight: 700;
        color: {accent};
        text-transform: uppercase;
        letter-spacing: 0.6px;
        padding: 2px 0;
    }}
    #CardSubtitleSoon {{
        font-size: 11px;
        font-weight: 700;
        color: #f59e0b;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        padding: 2px 0;
    }}

    /* Separador */
    #CardSeparator {{ color: #e2e8f0; max-height: 1px; }}
    #GeoMetadataDialog[theme="dark"] #CardSeparator {{ color: #334155; }}

    /* Descrição */
    #CardDescription {{
        font-size: 12px;
        color: #475569;
        line-height: 1.6;
    }}
    #GeoMetadataDialog[theme="dark"] #CardDescription {{ color: #94a3b8; }}

    /* Bullet de funcionalidade */
    #CardBullet {{
        color: {accent};
        font-weight: 900;
        font-size: 14px;
    }}
    #CardBulletSoon {{
        color: #f59e0b;
        font-weight: 900;
        font-size: 14px;
    }}

    #CardFeature {{
        font-size: 12px;
        color: #334155;
    }}
    #GeoMetadataDialog[theme="dark"] #CardFeature {{ color: #94a3b8; }}

    /* Botão de ação do card */
    #CardButton {{
        background-color: {accent};
        color: #ffffff;
        font-size: 13px;
        font-weight: 700;
        border: none;
        border-radius: 10px;
        padding: 11px 0;
    }}
    #CardButton:hover  {{ background-color: {accent_hover}; }}
    #CardButton:pressed {{ background-color: {accent_hover}; }}

    #CardButtonSoon {{
        background-color: transparent;
        color: #94a3b8;
        font-size: 13px;
        font-weight: 600;
        border: 2px solid #e2e8f0;
        border-radius: 10px;
        padding: 11px 0;
    }}
    #GeoMetadataDialog[theme="dark"] #CardButton {{
        background-color: {accent};
        color: #ffffff;
    }}
    #GeoMetadataDialog[theme="dark"] #CardButtonSoon {{
        border-color: #334155;
        color: #475569;
    }}
"""


# Compatibilidade retroativa — para qualquer import antigo de STYLE_SHEET
STYLE_SHEET = get_stylesheet(":/plugins/geometadata/img")

# styles.py

def get_stylesheet(img_dir: str) -> str:
    """
    Retorna o QSS completo do plugin.
    img_dir: caminho absoluto para a pasta img/ (forward-slashes).
    """
    img = img_dir.replace("\\", "/")

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

    /* Botões de menu dropdown (Arquivo, Conectividade Geohab) */
    #HeaderDropdownButton {{
        background-color: transparent;
        color: #475569;
        font-size: 14px;
        font-weight: 600;
        border: none;
        border-bottom: 3px solid transparent;
        padding: 10px 16px;
        margin: 0 2px;
    }}
    #HeaderDropdownButton:hover {{
        color: #0f172a;
        border-bottom: 3px solid #2563eb;
        background-color: transparent;
    }}
    #HeaderDropdownButton:pressed {{
        color: #2563eb;
        border-bottom: 3px solid #2563eb;
    }}
    #HeaderDropdownButton::menu-indicator {{ width: 0; image: none; }}

    #GeoMetadataDialog[theme="dark"] #HeaderDropdownButton {{ color: #94a3b8; }}
    #GeoMetadataDialog[theme="dark"] #HeaderDropdownButton:hover {{
        color: #f1f5f9;
        border-bottom: 3px solid #38bdf8;
    }}
    #GeoMetadataDialog[theme="dark"] #HeaderDropdownButton:pressed {{
        color: #38bdf8;
        border-bottom: 3px solid #38bdf8;
    }}

    /* Botão de login */
    #ConnectButton {{
        background-color: transparent;
        color: #2563eb;
        font-weight: 700;
        font-size: 12px;
        border: 2px solid #2563eb;
        border-radius: 8px;
        padding: 6px 16px;
    }}
    #ConnectButton:hover {{ background-color: #eff6ff; }}
    #GeoMetadataDialog[theme="dark"] #ConnectButton {{
        color: #38bdf8;
        border-color: #38bdf8;
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
        border-radius: 10px;
        padding: 6px 0;
    }}
    #DropdownMenu::item {{
        color: #1e293b;
        font-size: 13px;
        padding: 10px 20px;
        border-radius: 6px;
        margin: 1px 6px;
    }}
    #DropdownMenu::item:selected {{
        background-color: #eff6ff;
        color: #1d4ed8;
    }}
    #DropdownMenu::item:disabled {{ color: #cbd5e1; }}
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
        border: none;
        border-top: 1px solid #e2e8f0;
        padding: 0 16px;
        text-align: left;
    }}
    #CollapsibleHeader:hover {{ background-color: #f1f5f9; }}

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
    #CollapsibleBody {{ background-color: #ffffff; }}

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
        padding: 7px 14px;
        color: #1e293b;
        font-size: 13px;
        selection-background-color: #3b82f6;
        selection-color: #ffffff;
    }}
    QTextEdit {{
        border-radius: 12px;
        padding: 10px 14px;
    }}
    QLineEdit:hover, QTextEdit:hover, QSpinBox:hover, QDateTimeEdit:hover,
    QDateEdit:hover, QTimeEdit:hover {{
        border-color: #bdbdbd;
    }}
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateTimeEdit:focus,
    QDateEdit:focus, QTimeEdit:focus {{
        border: 2px solid #3b82f6;
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
        padding: 7px 34px 7px 14px;
        color: #1e293b;
        font-size: 13px;
        min-height: 18px;
        max-height: 18px;
    }}
    QComboBox:hover {{ border-color: #bdbdbd; }}
    QComboBox:focus {{ border: 2px solid #3b82f6; padding: 6px 33px 6px 13px; }}
    QComboBox:on    {{ border-color: #3b82f6; border-radius: 8px; }}
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
        border-radius: 10px;
        padding: 6px;
        selection-background-color: #eff6ff;
        selection-color: #1d4ed8;
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 10px 14px;
        border-radius: 8px;
        min-height: 30px;
        color: #1e293b;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: #f5f5f5;
    }}
    QComboBox QAbstractItemView::item:selected {{
        background-color: #eff6ff;
        color: #1d4ed8;
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
    #ContactCell:focus  {{ border: 2px solid #3b82f6; background: #ffffff; }}
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
        border: 2px solid #3b82f6;
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
        background-color: #2563eb;
        color: #ffffff;
        font-size: 18px;
        font-weight: bold;
        border: none;
        border-radius: 8px;
        padding: 0;
    }}
    #AddContactButton:hover   {{ background-color: #1d4ed8; }}
    #AddContactButton:pressed {{ background-color: #1e40af; }}

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
        background: transparent;
        border: none;
    }}

    /* Painel de conteúdo das abas */
    #FormTabs QTabWidget::pane {{
        border: none;
        border-top: 2px solid #e2e8f0;
        background-color: #ffffff;
    }}

    /* Barra de abas */
    #FormTabs QTabBar {{
        background: transparent;
    }}
    #FormTabs QTabBar::tab {{
        background: transparent;
        color: #64748b;
        font-size: 13px;
        font-weight: 600;
        padding: 10px 20px;
        border: none;
        border-bottom: 2px solid transparent;
        margin-right: 2px;
    }}
    #FormTabs QTabBar::tab:hover {{
        color: #334155;
        background: #f8fafc;
        border-bottom: 2px solid #cbd5e1;
    }}
    #FormTabs QTabBar::tab:selected {{
        color: #2563eb;
        background: transparent;
        border-bottom: 2px solid #2563eb;
    }}
    #FormTabs QTabBar::tab:disabled {{
        color: #cbd5e1;
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
"""


# Compatibilidade retroativa — para qualquer import antigo de STYLE_SHEET
STYLE_SHEET = get_stylesheet(":/plugins/geometadata/img")

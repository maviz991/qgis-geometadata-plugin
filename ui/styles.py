# styles.py

STYLE_SHEET = """
    * {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    /*******************************************************
     * TEMA CLARO (BASE PREMIUM)
     *******************************************************/
    #GeoMetadataDialog[theme="light"] {
        background-color: #f8fafc; /* Fundo cinza super claro (tipo tailwind slate-50) */
    }

    #Header {
        background-color: #ffffff;
        padding: 5px 15px;
        border-bottom: 1px solid #e2e8f0;
    }

    /* Estilo base para os botões de navegação */
    #HeaderButtonSave, #HeaderButtonXml, #HeaderButtonGeo, #HeaderButtonAddLayer {
        background-color: transparent;
        color: #475569;
        font-size: 14px;
        font-weight: 600;
        border: none;
        border-bottom: 2px solid transparent; 
        padding: 10px 10px;
        margin: 0 5px;
        width: 200px;
        max-width: 200px;
        text-align: center;
    }
    #HeaderButtonSave:hover, #HeaderButtonXml:hover, #HeaderButtonGeo:hover, #HeaderButtonAddLayer:hover {
        color: #0f172a;
        background-color: #f1f5f9;
        border-radius: 6px;
        border-bottom: 2px solid transparent; /* Removemos a linha em baixo para um botão flat redondo */
    }
    #HeaderButtonSave:disabled, #HeaderButtonXml:disabled, #HeaderButtonGeo:disabled, #HeaderButtonAddLayer:disabled {
        color: #cbd5e1;
    }
    
    /* Ícones para o tema claro */
    #HeaderButtonSave { icon: url(:/plugins/geometadata/img/exp_save_icon.png); }
    #HeaderButtonSave:hover { icon: url(:/plugins/geometadata/img/exp_save_icon_hover.png); }
    #HeaderButtonXml { icon: url(:/plugins/geometadata/img/exp_xml_icon.png); }
    #HeaderButtonXml:hover { icon: url(:/plugins/geometadata/img/exp_xml_icon_hover.png); }
    #HeaderButtonGeo { icon: url(:/plugins/geometadata/img/exp_geo_icon.png); }
    #HeaderButtonGeo:hover { icon: url(:/plugins/geometadata/img/exp_geo_icon_hover.png); }
    #HeaderButtonAddLayer { icon: url(:/plugins/geometadata/img/addlayer_icon.png); }
    #HeaderButtonAddLayer:hover { icon: url(:/plugins/geometadata/img/addlayer_icon_hover.png); }

    /* Botão de Conectar Premium */
    #Header #ConnectButton {
        background-color: #ffffff;
        color: #2563eb;
        font-weight: bold;
        font-size: 12px;
        border: 2px solid #2563eb;
        border-radius: 6px;
        padding: 6px 12px;
        margin-left: 10px;
    }
    #Header #ConnectButton:hover {
        background-color: #eff6ff;
    }

    /* Badge INATIVO (CINZA) */
    #wms_badge, #wfs_badge {
        background-color: #f1f5f9; 
        color: #64748b; 
        font-weight: 700;
        font-size: 11px;
        padding: 4px 8px;
        border-radius: 12px;
        min-width: 35px;
        max-width: 35px;
        text-align: center;
    }

    /* Badge ATIVO (Verde) */
    #wms_badge[active="true"], 
    #wfs_badge[active="true"] {
        background-color: #10b981;
        color: white;
    }

    /* Card principal do formulário */
    QWidget[class="Card"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
    }

    /* Força o conteúdo do .ui a ser transparente */
    QWidget#GeoMetadata_dialog_base {
        background-color: transparent;
    }

    /* =======================================================
       Estilização Global de Inputs (The "Web Face-lift")
       ======================================================= */
    QLabel {
        color: #334155;
        font-weight: 500;
        font-size: 12px;
    }
    
    QLineEdit, QTextEdit, QSpinBox, QComboBox, QDateTimeEdit {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 6px 10px;
        color: #1e293b;
        font-size: 13px;
        selection-background-color: #3b82f6;
    }
    
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus, QDateTimeEdit:focus {
        border: 1px solid #3b82f6;
    }
    
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 20px;
        border-left-width: 0px;
        border-top-right-radius: 3px;
        border-bottom-right-radius: 3px;
    }

    /*******************************************************
     * TEMA ESCURO (DARK MODE FLUÍDO)
     *******************************************************/
    QWidget#GeoMetadataDialog[theme="dark"] {
        background-color: #0f172a; /* Slate 900 */
    }

    QWidget#GeoMetadataDialog[theme="dark"] #Header {
        background-color: #1e293b;
        border-bottom: 1px solid #334155;
    }

    /* Botões de navegação no tema escuro */
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer {
        color: #94a3b8;
    }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave:hover,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml:hover,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo:hover,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer:hover {
        color: #f8fafc;
        background-color: #334155;
    }

    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave:disabled,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml:disabled,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo:disabled,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer:disabled {
        color: #475569; 
    }

    /* Ícones escuros */
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave { icon: url(:/plugins/geometadata/img/exp_save_icon_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave:hover { icon: url(:/plugins/geometadata/img/exp_save_icon_hover_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml { icon: url(:/plugins/geometadata/img/exp_xml_icon_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml:hover { icon: url(:/plugins/geometadata/img/exp_xml_icon_hover_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo { icon: url(:/plugins/geometadata/img/exp_geo_icon_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo:hover { icon: url(:/plugins/geometadata/img/exp_geo_icon_hover_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer { icon: url(:/plugins/geometadata/img/addlayer_icon_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer:hover { icon: url(:/plugins/geometadata/img/addlayer_icon_hover_white.png); }

    QWidget#GeoMetadataDialog[theme="dark"] #Header #ConnectButton {
        background-color: transparent;
        color: #38bdf8;
        border: 2px solid #38bdf8;
    }
    QWidget#GeoMetadataDialog[theme="dark"] #Header #ConnectButton:hover {
        background-color: rgba(56, 189, 248, 0.1);
    }

    QWidget#GeoMetadataDialog[theme="dark"] QWidget[class="Card"] {
        background-color: #1e293b;
        border: 1px solid #334155;
    }

    /* Estilos globais para text/inputs dark */
    QWidget#GeoMetadataDialog[theme="dark"] QLabel {
        color: #cbd5e1;
    }
    QWidget#GeoMetadataDialog[theme="dark"] QLineEdit,
    QWidget#GeoMetadataDialog[theme="dark"] QTextEdit,
    QWidget#GeoMetadataDialog[theme="dark"] QSpinBox,
    QWidget#GeoMetadataDialog[theme="dark"] QComboBox,
    QWidget#GeoMetadataDialog[theme="dark"] QDateTimeEdit {
        background-color: #0f172a;
        color: #f1f5f9;
        border: 1px solid #334155;
    }
    QWidget#GeoMetadataDialog[theme="dark"] QLineEdit:focus,
    QWidget#GeoMetadataDialog[theme="dark"] QTextEdit:focus,
    QWidget#GeoMetadataDialog[theme="dark"] QSpinBox:focus,
    QWidget#GeoMetadataDialog[theme="dark"] QComboBox:focus,
    QWidget#GeoMetadataDialog[theme="dark"] QDateTimeEdit:focus {
        border: 1px solid #38bdf8;
    }

    /* Painel WMS / WFS */
    QWidget#GeoMetadataDialog[theme="dark"] QGroupBox#DistributionPanel {
        background-color: #0f172a;
        border: 1px solid #334155;
        border-radius: 8px;
    }
    QWidget#GeoMetadataDialog[theme="dark"] QGroupBox#DistributionPanel::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        color: #94a3b8;
    }

    QWidget#GeoMetadataDialog[theme="dark"] #wms_badge, 
    QWidget#GeoMetadataDialog[theme="dark"] #wfs_badge {
        background-color: #334155;
        color: #94a3b8; 
    }
    QWidget#GeoMetadataDialog[theme="dark"] #wms_badge[active="true"], 
    QWidget#GeoMetadataDialog[theme="dark"] #wfs_badge[active="true"] {
        background-color: #10b981;
        color: white;
    }
"""

# styles.py

STYLE_SHEET = """
    /*******************************************************
     * TEMA CLARO (BASE)
     *******************************************************/
    #GeoMetadataDialog[theme="light"] {
        background-color: #f4f4f4; /* Fundo cinza claro para o diálogo */
    }

    #Header {
        background-color: #ffffff;
        padding: 5px 15px;
        border-bottom: 1px solid #e0e0e0;
    }

    /* Estilo base para os botões de navegação */
    #HeaderButtonSave, #HeaderButtonXml, #HeaderButtonGeo, #HeaderButtonAddLayer {
        background-color: transparent;
        color: rgba(0, 0, 0, 0.7);
        font-size: 15px;
        font-weight: bold;
        border: none;
        border-bottom: 1.5px solid transparent; 
        padding: 12px 0px;
        margin: 0 5px;
        min-width: 195px;
        text-align: center;
    }
    #HeaderButtonSave:hover, #HeaderButtonXml:hover, #HeaderButtonGeo:hover, #HeaderButtonAddLayer:hover {
        color: #000000;
        border-bottom: 1.5px solid rgba(0, 0, 0, 0.7);
    }
    #HeaderButtonSave:disabled, #HeaderButtonXml:disabled, #HeaderButtonGeo:disabled, #HeaderButtonAddLayer:disabled {
        color: #cccccc;
        border-bottom: 1.5px solid transparent;
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

    /* Botão de Conectar */
    #Header #ConnectButton {
        background-color: #111111;
        color: white;
        font-weight: bold;
        font-size: 11px;
        border: none;
        border-radius: 5px;
        padding: 5px 6px;
        margin-left: 10px;
    }
    #Header #ConnectButton:hover {
        background-color: rgba(0, 0, 0, 0.75);
    }
        /* Badge INATIVO (CINZA) */
    #wms_badge, #wfs_badge {
        background-color: #EAECEE; 
        color: #7F8C8D; 
        font-weight: bold;
        padding: 3px 8px;
        border-radius: 4px;
        margin-right: 1px;
        min-width: 35px;
        max-width: 35px;
        min-height: 15px;
        max-height: 15px;        
        text-align: auto;
    }

    /* Badge ATIVO (Verde) */
    #wms_badge[active="true"], 
    #wfs_badge[active="true"] {
        background-color: #008959;
        color: white;
        font-weight: bold;
    }

    /* Card principal do formulário */
    QWidget[class="Card"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
    }

    /* Força o conteúdo do .ui a ser transparente */
    QWidget#GeoMetadata_dialog_base {
        background-color: transparent;
    }


    /*******************************************************
     * SOBRESCREVE PARA O TEMA ESCURO
     * Estas regras só se aplicam quando o diálogo tem a propriedade [theme="dark"]
     *******************************************************/
    
    /* Fundo geral do diálogo */
    QWidget#GeoMetadataDialog[theme="dark"] {
        background-color: #222222; /* Fundo escuro principal */
    }

    /* Header no tema escuro */
    QWidget#GeoMetadataDialog[theme="dark"] #Header {
        background-color: #2b2b2b;
        border-bottom: 1px solid #444;
    }

    /* Botões de navegação no tema escuro */
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer {
        color: #cccccc; /* Texto claro */
    }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave:hover,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml:hover,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo:hover,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer:hover {
        color: #ffffff; /* Texto branco no hover */
        border-bottom: 1.5px solid #cccccc;
    }

    /* Botões de navegação DESABILITADOS no tema escuro */
    /* A verificação [theme="dark"] agora está no widget pai correto */
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave:disabled,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml:disabled,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo:disabled,
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer:disabled {
        color: #555555; /* Um cinza mais claro para melhor visibilidade no fundo escuro */
        border-bottom: 1.5px solid transparent;
    }

    /* Ícones para o tema claro */
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave { icon: url(:/plugins/geometadata/img/exp_save_icon_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonSave:hover { icon: url(:/plugins/geometadata/img/exp_save_icon_hover_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml { icon: url(:/plugins/geometadata/img/exp_xml_icon_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonXml:hover { icon: url(:/plugins/geometadata/img/exp_xml_icon_hover_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo { icon: url(:/plugins/geometadata/img/exp_geo_icon_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonGeo:hover { icon: url(:/plugins/geometadata/img/exp_geo_icon_hover_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer { icon: url(:/plugins/geometadata/img/addlayer_icon_white.png); }
    QWidget#GeoMetadataDialog[theme="dark"] #HeaderButtonAddLayer:hover { icon: url(:/plugins/geometadata/img/addlayer_icon_hover_white.png); }


    /* Botão de Conectar no tema escuro */
    QWidget#GeoMetadataDialog[theme="dark"] #Header #ConnectButton {
        background-color: #555;
        color: #eee;
    }
    QWidget#GeoMetadataDialog[theme="dark"] #Header #ConnectButton:hover {
        background-color: #666;
    }

    /* Card principal no tema escuro */
    QWidget#GeoMetadataDialog[theme="dark"] QWidget[class="Card"] {
        background-color: #333333;
        border: 1px solid #4e4e4e;
    }

    /* Estilos globais para widgets de texto e labels no tema escuro */
    QWidget#GeoMetadataDialog[theme="dark"] QLabel {
        color: #ccc;
    }
    QWidget#GeoMetadataDialog[theme="dark"] QLineEdit,
    QWidget#GeoMetadataDialog[theme="dark"] QTextEdit,
    QWidget#GeoMetadataDialog[theme="dark"] QSpinBox,
    QWidget#GeoMetadataDialog[theme="dark"] QDateTimeEdit {
        background-color: #2a2a2a;
        color: #eee;
        border: 1px solid #555;
        border-radius: 4px;
        padding: 3px;
    }
    /* Painel de distribuição no tema escuro */
    /* Badges no tema escuro */
    QWidget#GeoMetadataDialog[theme="dark"] #wms_badge, 
    QWidget#GeoMetadataDialog[theme="dark"] #wfs_badge {
        background-color: #4f4f4f; 
        color: #ccc; 
    }
    QWidget#GeoMetadataDialog[theme="dark"] #wms_badge[active="true"], 
    QWidget#GeoMetadataDialog[theme="dark"] #wfs_badge[active="true"] {
        background-color: #008959;
        color: white;
    }
"""


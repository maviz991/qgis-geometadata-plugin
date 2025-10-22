STYLE_SHEET = """
    #GeoMetadataDialog {
        background-color: #f4f4f4;
    }

    /* O Header */
    #Header {
        background-color: #ffffffff;
        padding: 5px 15px;
        border-bottom: 1px solid #e0e0e0;
    }

    /* --- ESTILOS DOS BOTÕES NO HEADER --- */

    /* 1. ESTILO BASE para os botões de navegação do header */
    /* Aplica-se a todos os botões pelos seus novos objectNames */
    #HeaderButtonSave, #HeaderButtonXml, #HeaderButtonGeo, #HeaderButtonAddLayer {
        background-color: transparent;
        color: rgba(0, 0, 0, 0.7);
        font-size: 15px;
        font-weight: bold;
        border: none;
        border-bottom: 1.5px solid transparent; 
        padding: 12px 0px; /* Padding ajustado para o ícone */
        margin: 0 5px;
        min-width: 195px;
        text-align: center;
    }

    /* 2. ESTILO HOVER para os botões de navegação */
    #HeaderButtonSave:hover, #HeaderButtonXml:hover, #HeaderButtonGeo:hover, #HeaderButtonAddLayer:hover {
        color: #000000;
        border-bottom: 1.5px solid rgba(0, 0, 0, 0.7);
    }

    /* 3. ESTILO DESABILITADO para os botões de navegação */
    #HeaderButtonSave:disabled, #HeaderButtonXml:disabled, #HeaderButtonGeo:disabled, #HeaderButtonAddLayer:disabled {
        color: #cccccc;
        border-bottom: 1.5px solid transparent;
    }

    /* 4. DEFINIÇÃO DOS ÍCONES (Normal e Hover) PARA CADA BOTÃO ESPECÍFICO */
    
    /* -- Botão Salvar -- */
    #HeaderButtonSave {
        icon: url(:/plugins/geometadata/img/exp_save_icon.png);
    }
    #HeaderButtonSave:hover {
        icon: url(:/plugins/geometadata/img/exp_save_icon_hover.png);
    }

    /* -- Botão Exportar XML -- */
    #HeaderButtonXml {
        icon: url(:/plugins/geometadata/img/exp_xml_icon.png);
    }
    #HeaderButtonXml:hover {
        icon: url(:/plugins/geometadata/img/exp_xml_icon_hover.png);
    }

    /* -- Botão Exportar Geohab -- */
    #HeaderButtonGeo {
        icon: url(:/plugins/geometadata/img/exp_geo_icon.png);
    }
    #HeaderButtonGeo:hover {
        icon: url(:/plugins/geometadata/img/exp_geo_icon_hover.png);
    }

    /* -- Botão Associar Camada -- */
    #HeaderButtonAddLayer {
        icon: url(:/plugins/geometadata/img/addlayer_icon.png);
    }
    #HeaderButtonAddLayer:hover {
        icon: url(:/plugins/geometadata/img/addlayer_icon_hover.png);
    }

    /* 2. Botão de Ação Principal ("Conectar") */
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

    /* Botão limpar */
    #ClearButton{
        color: white;
        font-weight: bold;
        border: transparent;
    }
    #ClearButton:hover {
        background-color: #FADBD8;
    }

    /* Card principal do formulário */
    .Card {
        background-color: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
    }
"""


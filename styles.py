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

    /* 1. Botões estilo "Link de Navegação" */
    #Header #LinkButton {
        background-color: transparent;
        color: #333;
        font-size: 15px;
        font-weight: bold;
        border: none;
        border-bottom: 2px solid transparent;
        padding: 8px 10px;
        margin: 0 5px;
    }
    #Header #LinkButton:hover {
        color: #c9302c; 
        border-bottom: 2px solid #c9302c; /* <-- Sublinhado vermelho no hover */
    }
    #Header #LinkButton:disabled {
        color: #cccccc;
        border-bottom: 2px solid transparent;
    }

    /* 2. Botão de Ação Principal ("Conectar") */
    #Header #ConnectButton {
        background-color: #111111;
        color: white;
        font-weight: bold;
        font-size: 10px;
        border: none;
        border-radius: 4px;
        padding: 8px 24px;
        margin-left: 10px;
    }
    #Header #ConnectButton:hover {
        background-color: #333333;
    }
    
    /* Estilo para quando o usuário está conectado */
    #Header #ConnectButton[loggedIn="true"] {
        background-color: #6c757d; /* Cinza para indicar estado "conectado" */
    }
    #Header #ConnectButton[loggedIn="true"]:hover {
        background-color: #5a6268;
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


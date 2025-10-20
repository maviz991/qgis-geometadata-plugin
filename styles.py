# Arquivo: styles.py (Versão Final e Sofisticada)

STYLE_SHEET = """
    #GeoMetadataDialog {
        background-color: #f4f4f4;
    }

    /* O Header */
    #Header {
        background-color: #ffffff;
        padding: 5px 15px; /* Diminuí o padding vertical para um header mais fino */
        border-bottom: 1px solid #e0e0e0;
    }

    /* --- ESTILOS DOS BOTÕES NO HEADER --- */

    /* 1. Botões estilo "Link de Navegação" */
    #Header #LinkButton {
        background-color: transparent;
        color: #333; /* Cor de texto padrão */
        font-weight: bold;
        border: none;
        padding: 8px 12px;
        margin: 0 5px;
        text-decoration: none; /* Garante que não há sublinhado no estado normal */
    }
    #Header #LinkButton:hover {
        color: #ff1100; /* Cor azul ao passar o mouse */
        text-decoration: underline; /* O sublinhado que você pediu! */
    }
    #Header #LinkButton:disabled {
        color: #cccccc; /* Cor para desabilitado */
        text-decoration: none;
    }

    /* 2. Botão de Status ("Associado a:") */
    #Header #DistributionButton {
        color: #555;
        padding: 6px 12px;
        font-weight: normal;
    }
    #Header #DistributionButton:disabled {
        background-color: #f8f8f8;
        color: #cccccc;
    }

    /* 3. Botão de Ação Principal ("Conectar") */
    #Header #ConnectButton {
        background-color: #007bff;
        color: white;
        font-weight: bold;
        border: none;
        border-radius: 4px;
        padding: 8px 16px;
        margin-left: 10px;
    }
    #Header #ConnectButton:hover {
        background-color: #0056b3;
    }
    #Header #ConnectButton:disabled {
        background-color: #c0c0c0;
    }
    #wms_badge, #wfs_badge {
        background-color: #1A5276;
        color: white;
        font-weight: bold;
        padding: 3px 8px;
        border-radius: 4px;
        margin-right: 10px;
        border: 1px solid red; /* <--- ADICIONE PARA DEPURAR */
    }

    /* O "Card" principal do formulário */
    .Card {
        background-color: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
    }
"""

# Arquivo: styles.py (Versão Final com Estilo Profissional)

STYLE_SHEET = """
    #GeoMetadataDialog {
        background-color: #f4f4f4;
    }

    /* O Header */
    #Header {
        background-color: #ffffff;
        padding: 5px 15px;
        border-bottom: 1px solid #e0e0e0;
    }

    /* --- ESTILOS DOS BOTÕES NO HEADER --- */

    /* 1. Botões estilo "Link de Navegação" */
    #Header #LinkButton {
        background-color: transparent;
        color: #333;
        font-size: 15px; /* <-- Texto maior */
        font-weight: bold;
        border: none;
        /* Truque para o sublinhado animado: uma borda transparente */
        border-bottom: 2px solid transparent;
        padding: 8px 10px;
        margin: 0 5px;
    }
    #Header #LinkButton:hover {
        color: #c9302c; /* <-- Cor vermelha no hover */
        border-bottom: 2px solid #c9302c; /* <-- Sublinhado vermelho no hover */
    }
    #Header #LinkButton:disabled {
        color: #cccccc;
        border-bottom: 2px solid transparent;
    }

    /* 2. Botão de Status ("Associado a:") */
    #Header #DistributionButton {
        background-color: #f0f0f0;
        color: #555;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        padding: 6px 12px;
        font-weight: normal;
    }
    #Header #DistributionButton:disabled {
        background-color: #f8f8f8;
        color: #cccccc;
    }

    /* 3. Botão de Ação Principal ("Conectar") */
    #Header #ConnectButton {
        background-color: #111111;
        color: white;
        font-weight: bold;
        border: none;
        border-radius: 4px;
        padding: 8px 24px;
        margin-left: 10px;
    }
    #Header #ConnectButton:hover {
        background-color: #333333;
    }
    
    /* Estilo especial para quando o usuário está conectado */
    #Header #ConnectButton[loggedIn="true"] {
        background-color: #6c757d; /* Cinza para indicar estado "conectado" */
    }
    #Header #ConnectButton[loggedIn="true"]:hover {
        background-color: #5a6268;
    }
    /* ESTILO PADRÃO (INATIVO / CINZA) */
    #wms_badge, #wfs_badge {
        background-color: #EAECEE; /* Um cinza bem claro */
        color: #7F8C8D; /* Um cinza mais escuro para o texto */
        font-weight: normal; /* Sem negrito quando inativo */
        padding: 3px 8px;
        border-radius: 4px;
        margin-right: 10px;
    }

        /* ESTILO ATIVO (COLORIDO) - SÓ APLICA QUANDO A PROPRIEDADE 'active' É 'true' */
    #wms_badge[active="true"], 
    #wfs_badge[active="true"] {
        background-color: #008959;
        color: white;
        font-weight: bold;
    }

    /* O "Card" principal do formulário */
    .Card {
        background-color: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
    }
"""
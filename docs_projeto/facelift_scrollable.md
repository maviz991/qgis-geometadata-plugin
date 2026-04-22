# Reestruturação Dinâmica do Formulário: Facelift Scrollable e Sub-Menus

## 1. O Problema da Abordagem Anterior
Inicialmente, o plugin utilizava um arquivo gigante criado no **Qt Designer** (`GeoMetadata_dialog_base.ui`), engessando os campos a uma tela fixa sem rolagem inteligente e impossibilitando a adição dinâmica de múltiplos parâmetros (como adicionar novos contatos ou autores durante a mesma sessão). A tentativa de usar HTML (via `QWebEngineView`) resultava frequentemente em um erro crítico (Tela Branca ou falta de bibliotecas no instalador base OSGeo4W).

## 2. Abordagem Geocat Inspirada (100% Nativo PyQt)
Para mantermos a estabilidade e ao mesmo tempo ganharmos uma interface profissional, usaremos:

1.  **Header com Dropdowns (Layout CDHU Web):**
    O Menu superior não terá mais botões pesados enfileirados, mas `QToolButton/QPushButton` associados a `QMenu`s (Opções de Arquivo, Conectividade Geohab) simulando o portal Web institucional.
2.  **O Fim do Formulário Fixo e Início do `QScrollArea`:**
    Os campos saem do contêiner isolado do Qt Designer e passam a habitar um `QScrollArea`. O formulário agora rola infinitamente para baixo.
3.  **Montador Dinâmico de Nós (Add Autores Infinitos):**
    Na seção de contatos, poderemos programar através do Python o acoplamento dinâmico de novos Formulários. Clicar no botão `[+] Adicionar Novo Autor` chamará uma função que injeta instantaneamente novos `QLineEdits` formatados na interface ativa sem destruir as conexões ativas.

### Etapas de Execução (Roadmap Interno)
*   **Fase 1:** Atualização da barra superior com funções de drop-down.
*   **Fase 2:** Quebra da dependência total da janela única. Isolamento dos campos base no Container que pode possuir rolamento (`QScrollArea`).
*   **Fase 3:** Implementar as classes visuais complementares. O `FormManager` orquestrará arrays dinâmicos de autores em vez de simples dicionários únicos.

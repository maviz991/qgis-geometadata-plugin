### **Instruções: Da Instalação à Primeira Execução**

---

#### **Etapa 1: Preparação do Ambiente de Desenvolvimento**

1.  **Abrir o Terminal Correto:** Abrimos o **"OSGeo4W Shell"** como administrador. Isso é crucial para usar o ambiente Python que vem com o QGIS, garantindo total compatibilidade.
2.  **Instalar o `pb_tool`:** Dentro do OSGeo4W Shell, executamos o comando para instalar a ferramenta de criação de plugins no ambiente do QGIS.
    ```bash
    python -m pip install pb_tool
    ```

---

#### **Etapa 2: Criação da Estrutura do Plugin (Método Correto)**

1.  **Navegar para a Pasta de Plugins:** Usamos o terminal para entrar no diretório onde o QGIS armazena os plugins do usuário.
    ```bash
    cd C:\Users\mdaviz\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins
    ```
2.  **Criar a Pasta do Plugin:** Criamos manualmente a pasta que conterá todos os arquivos do nosso projeto para manter tudo organizado.
    ```bash
    mkdir GeoMetadata
    ```
3.  **Entrar na Nova Pasta:** Acessamos o diretório recém-criado.
    ```bash
    cd GeoMetadata
    ```
4.  **Executar o `pb_tool`:** De dentro da pasta `GeoMetadata`, executamos o comando para gerar o esqueleto do plugin, usando os parâmetros corretos (`--modulename` e `--classname`). O `.` no final instruiu a ferramenta a criar os arquivos no diretório atual.
    ```bash
    pb_tool create --modulename "GeoMetadata" --classname "GeoMetadata" .
    ```
5.  **Responder às Perguntas:** Respondemos às perguntas interativas para preencher as informações básicas do plugin (nome do menu, descrição, autor, etc.).

---

#### **Etapa 3: Ativação e Teste no QGIS**

1.  **Abrir o QGIS:** Iniciamos o QGIS para que ele pudesse detectar a nova pasta do plugin.
2.  **Instalar o Plugin Reloader:** Pelo gerenciador de plugins do QGIS, instalamos o `Plugin Reloader`, uma ferramenta essencial para o desenvolvimento que nos permite recarregar nosso plugin sem reiniciar o QGIS.
3.  **Ativar o "GeoMetadata":** Fomos em `Plugins > Gerenciar e Instalar Plugins...`, na aba "Instalados", encontramos o "GeoMetadata" e marcamos a caixa para ativá-lo.
4.  **Verificar o Funcionamento:** Clicamos no novo ícone do "GeoMetadata" que apareceu na barra de ferramentas. Uma pequena janela vazia abriu, confirmando que o plugin foi carregado com sucesso.

---

#### **Etapa 4: Início do Design da Interface (Ponto Atual)**

1.  **Abrir o Qt Designer:** Localizamos e abrimos o programa "Designer", que vem com o QGIS.
2.  **Abrir o Arquivo de UI:** Dentro do Designer, abrimos o arquivo `geometadata_dialog_base.ui` localizado na pasta do nosso plugin.
3.  **Próxima Ação:** Agora estamos prontos para arrastar e soltar componentes (como caixas de texto, rótulos e botões) para desenhar o formulário de metadados.

Você completou toda a configuração e a criação da base. O próximo passo é focar exclusivamente no Qt Designer para construir a interface visual do seu plugin.

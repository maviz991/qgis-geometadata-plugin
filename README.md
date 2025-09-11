# qgis-geometadata-plugin

 # GeoMetadata - Plugin de Metadados para QGIS

![Logo do Plugin](icon.png)

Um plugin para o QGIS desenhado para simplificar a criação e publicação de metadados no padrão MGB 2.0, com integração direta com o catálogo de metadados Geoportal - Geohah|CDHU (GeoNetwork).

## Funcionalidades

*   **Formulário Intuitivo:** Interface gráfica baseada nos campos do padrão MGB 2.0.
*   **Preenchimento Automático:** Preenche automaticamente o Título e a Extensão Geográfica (BBOX) a partir da camada selecionada.
*   **Contatos Pré-definidos:** Acelera o preenchimento com uma lista de contatos comuns (CDHU, SSARU, etc.).
*   **Persistência de Dados:** Salve seu trabalho e continue depois. O plugin salva um arquivo XML ao lado da sua camada.
*   **Exportação para XML:** Gera um arquivo XML no padrão MGB 2.0, pronto para ser usado em outros sistemas.
*   **Publicação Direta:** Exporte seus metadados diretamente para o Geoportal - Geohab|CDHU (GeoNetwork) com um clique.

## Instalação

1.  Baixe a última versão do plugin na [página de Releases](https://github.com/maviz991/qgis-geometadata-plugin/releases).
2.  No QGIS, vá em `Plugins > Gerenciar e Instalar Plugins...`.
3.  Selecione a opção "Instalar a partir de ZIP" e escolha o arquivo que você baixou.
4.  Ative o plugin "GeoMetadata" na lista de plugins instalados.

## Como Usar

1.  **Selecione uma Camada:** Clique em uma camada vetorial no painel de camadas do QGIS.
2.  **Abra o Plugin:** Clique no ícone do GeoMetadata (Geohab) na barra de ferramentas.
3.  **Preencha os Campos:** O formulário será pré-preenchido com dados da camada. Complete ou ajuste os outros campos.
4.  **Salve ou Exporte:**
    *   **Salvar:** Cria um arquivo `.xml` na mesma pasta da sua camada para que você possa continuar o trabalho depois.
    *   **Exportar para XML:** Pede um local para salvar um arquivo `.xml` independente.
    *   **Exportar para Geohab|CDHU:** Abre uma janela de login para que você possa publicar os metadados diretamente no catálogo.

## Desenvolvimento

(Instruções para desenvolvedores que queiram contribuir: como configurar o ambiente, dependências, etc.)

## Licença

Este projeto é licenciado sob a licença GPL 2.0.




# Projeto do plugin
##1. Stack de Tecnologia (100% Gratuito e Open Source):
- Linguagem: Python 3 (o QGIS já vem com um ambiente Python embutido).
- Interface Gráfica (UI): PyQt5/PyQt6 (a biblioteca que o QGIS usa para suas janelas). O design da UI será feito com o Qt Designer.
- API do QGIS: PyQGIS (para interagir com as camadas, a interface do QGIS, etc.).
- Manipulação de XML: A biblioteca padrão do Python xml.etree.ElementTree é perfeita para isso.
- Comunicação com API (Geoportal): A biblioteca requests (se não vier com o Python do QGIS, pode ser adicionada).
- Ferramentas de Desenvolvimento:
- VS Code: Ótima escolha. Instale a extensão "Python" da Microsoft.
- QGIS: Para testar o plugin em tempo real.
- Plugin Reloader: Um plugin para o QGIS essencial para desenvolvimento. Ele permite recarregar seu plugin sem precisar reiniciar o QGIS a cada alteração no código. Instale-o pelo gerenciador de plugins do QGIS.
- pb_tool: Uma ferramenta de linha de comando para criar a estrutura básica do plugin, compilar a interface e empacotar para distribuição. É um padrão da comunidade.

##2. Fluxo de Trabalho do Usuário (Como o plugin vai funcionar):
- O usuário seleciona uma camada no painel de camadas do QGIS.
- Clica no ícone do nosso plugin "GeoMetadata" na barra de ferramentas.
- Uma janela (o formulário de metadados) se abre.
- Se já existem metadados associados àquela camada, os campos do formulário são preenchidos.
- Se não, o formulário aparece em branco (ou com valores padrão).
- O usuário preenche os campos obrigatórios do MGB (e os opcionais que desejar).
- O usuário tem 3 opções:
- Salvar: Salva os metadados em um arquivo "sidecar" (um arquivo que fica ao lado do arquivo da camada, ex: minhacamada.shp.xml). Isso associa os metadados à camada de forma persistente.
- Exportar para XML (MGB 2.0): Pega os dados do formulário, usa a lógica do seu script para gerar o XML no padrão MGB 2.0 e pede ao usuário um local para salvar este arquivo .xml.
- Exportar para Geoportal: Pega os dados, formata no padrão que a API do Geohab exige (provavelmente JSON ou XML) e envia via requisição HTTP.

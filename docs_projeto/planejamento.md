# Planejamento do Plugin GeoMetadata - Histórico (v1.x)

> **[HISTÓRICO]** Este documento registra a concepção original e o estado atual (v1.0.1) do plugin.
> Para o plano de evolução para v2.0, consulte `requisitos_v2.md`.

---

## Stack de Tecnologia (100% Gratuito e Open Source)

- **Linguagem:** Python 3 (ambiente Python do QGIS)
- **Interface Gráfica:** PyQt5 (via `qgis.PyQt`) + Qt Designer para `.ui`
- **API do QGIS:** PyQGIS (`iface`, `QgsProject`, `QgsCoordinateTransform`, etc.)
- **Manipulação de XML:** `lxml` + `xml.etree` (geração e parsing de MGB 2.0)
- **Comunicação HTTP:** `requests` (chamadas à API REST do GeoNetwork/GeoServer)
- **Banco de Dados:** `psycopg2` (persistência em PostgreSQL para camadas PostGIS)

### Ferramentas de Desenvolvimento

- VS Code + extensão Python
- OSGeo4W Shell (ambiente Python do QGIS)
- Plugin Reloader (reload sem reiniciar QGIS)
- `pb_tool` para empacotamento

---

## Fluxo de Trabalho Atual (v1.0.1 - Em Produção)

1. Usuário seleciona uma camada no painel de camadas do QGIS.
2. Abre o plugin `GeoMetadata` pela barra de ferramentas.
3. O formulário carrega com campos pré-preenchidos (título, BBox, UUID) se já houver metadado associado.
4. Usuário preenche os campos MGB 2.0.
5. Ações disponíveis:
   - **Continuar depois** - Salva em arquivo sidecar (`.xml` ao lado do shapefile) ou em tabela PostgreSQL.
   - **Exportar Metadado** - Gera XML MGB 2.0 e salva localmente.
   - **Exportar para Geohab** - Envia via REST API ao GeoNetwork (requer login).
   - **Associar Camada** - Vincula URLs WMS/WFS ao metadado.

---

## Módulos Implementados (v1.0.1)

| Arquivo | Função |
|---|---|
| `GeoMetadata.py` | Entry point do plugin QGIS |
| `GeoMetadata_dialog.py` | Dialog principal + toda lógica do formulário |
| `GeoMetadata_dialog_base.ui` | Layout Qt Designer do formulário |
| `unified_login_dialog.py` | Login HTTP Basic Auth + suporte a QgsAuthConfigSelect |
| `unified_login_dialog_base.ui` | Layout Qt Designer do diálogo de login |
| `layer_selection_dialog.py` | Seletor de camadas WMS/WFS para associação |
| `layer_selection_dialog_base.ui` | Layout Qt Designer do seletor |
| `xml_generator.py` | Geração de XML MGB 2.0 a partir de template |
| `xml_parser.py` | Leitura de XML existente para preencher formulário |
| `tamplate_mgb20.xml` | Template base MGB 2.0 |
| `plugin_config.py` | Singleton de configuração (lê `config.json`) |
| `config.json` | URLs de GeoNetwork e GeoServer do ambiente |
| `styles.py` | QSS para tema claro/escuro |
| `contacts.json` | Contatos pré-definidos por departamento |

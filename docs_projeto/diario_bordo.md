# Diário de Bordo: Evolução GeoMetadata
**Mantenedor:** Agente de Documentação  
**Última Atualização:** 17/04/2026

---

## Estado Atual do Plugin

**Versão em Produção:** `1.0.1`  
**Versão em Desenvolvimento:** `2.0.0`  
**Ambiente DEV:** `https://geo-d.cdhu.sp.gov.br`

---

## Registro 1 — Consolidação da Base e Limpeza (17/04/2026)

### Contexto
Análise do repositório identificou dois arquivos obsoletos coexistindo com o código de produção, gerando confusão arquitetural sobre o mecanismo de autenticação adotado.

### Decisões Tomadas

**Remoção de arquivos obsoletos:**
- `auth_webview.py` — Protótipo experimental de Cookie Trapping via `QWebEngineView`. Nunca integrado ao fluxo principal. **Removido.**
- `geoserver_login_dialog.py` — Diálogo legado de login GeoServer, substituído pelo `UnifiedLoginDialog`. **Removido.**

**Mecanismo de autenticação confirmado para v2.0:**
- O `UnifiedLoginDialog` com **Basic Auth** (`requests.Session`) é o mecanismo de produção vigente e será mantido na v2.0.
- A abordagem via Cookie Trapping / GeoOrchestra / Entra ID depende de decisões de infraestrutura pelo time de TI e está em **backlog**.

**Consolidação documental:**
- `planejamento.md` → Convertido para documento histórico (escopo v1.x).
- `planejamento_geometadata_v2.md` → Descontinuado (conteúdo absorvido pelo `requisitos_v2.md`).
- `requisitos_dev-v_1-0-3.md` → Substituído pelo `requisitos_v2.md` (nomenclatura corrigida).
- `requisitos_v2.md` → Novo documento consolidado de requisitos e plano de implementação para v2.0.

---

## Registro 2 — Definição da Arquitetura v2.0 (17/04/2026)

### Decisões de Arquitetura

**Gateway e Comunicação:**
Toda comunicação passa pelo Gateway GeoOrchestra (`geo-d.cdhu.sp.gov.br`), que roteia para GeoServer e GeoNetwork nos seus paths respectivos. A autenticação é Basic Auth, e os cookies XSRF-TOKEN/JSESSIONID do GeoNetwork são capturados e injetados automaticamente via `requests.Session`.

**Novo Módulo — `geoserver_publisher.py`:**
Classe centralizada para encapsular todas as chamadas à REST API do GeoServer. Mantém a mesma `requests.Session` autenticada usada na sessão atual do plugin.

**Publicação Multimodal:**
- **Publicação Lógica (PostGIS):** Para camadas já no banco — envia apenas o comando `FeatureType` REST. Zero tráfego de dados.
- **Upload (Shapefile ZIP):** Para camadas locais — empacota e envia via REST. Operação em `QThread`.

**Exportação SLD:**
Usa `QgsMapLayer.exportSldStyle()` nativo do QGIS. É explicitamente *best-effort* — o plugin avisará que estilos complexos podem ter fidelidade reduzida.

**MinIO em Backlog:**
A integração com MinIO para upload de rasters aguarda definição de Service Account e credenciais separadas pelo time de TI. A dependência `boto3` **não será incluída** nos requisitos de instalação da v2.0.

### Próximos Passos
1. Criar `geoserver_publisher.py` com os métodos base (listagem, publicação lógica, upload).
2. Criar a aba/wizard de publicação GeoServer na UI principal.
3. Implementar `QThread` para operações de upload.
4. Expor o `xml_parser.py` via botão na UI para abertura de XMLs externos.

---

## Registro 3 — Mudança de Prioridade: Entra ID (22/04/2026)

### Contexto
Discussão técnica sobre a viabilidade de implementar a autenticação moderna (SSO) logo no início da v2.0, evitando retrabalho futuro em módulos que dependem da sessão autenticada.

### Decisões Tomadas

1. **Priorização do Entra ID:** A autenticação via Microsoft Entra ID (Azure AD) foi movida para a **Fase 1** do projeto. 
2. **Integração GeoOrchestra:** Confirmado que o ambiente GeoOrchestra já possui integração com Entra ID, o que facilita o processo. O plugin atuará como um *Public Client* usando o fluxo OAuth2 + PKCE.
3. **Criação de Documento Tecnico:** Elaborado o arquivo `solicitacao_ti_entra_id.md` contendo todas as especificações necessárias (App Registration, Redirect URI, Escopos) para ser enviado ao setor de TI.
4. **Resgate de Auth Fallback:** O mecanismo de Basic Auth será mantido como fallback inicial e para garantir a compatibilidade enquanto a infraestrutura do Azure é configurada.

### Próximos Passos
1. Enviar solicitação ao TI conforme `solicitacao_ti_entra_id.md`.
2. Criar a camada de abstração `AuthProvider` no plugin para suportar múltiplos métodos de autenticação.
3. Iniciar a implementação da biblioteca `msal-python` no ambiente de desenvolvimento.

---

*Adicione novos registros abaixo conforme o desenvolvimento avança.*

### 22/04/2026 — Facelift Completo (IMPLEMENTADO)

#### Decisão Arquitetural Central
**`GeoMetadata_dialog_base.ui` foi abandonado.** O formulário é agora 100% Python/PyQt dinâmico, sem dependência do Qt Designer. O `.ui` pode ser deletado do repositório.

#### O que foi criado/modificado

| Arquivo | Mudança |
|---|---|
| `ui/dynamic_form.py` | **NOVO** — Formulário completo em Python. `DynamicForm` + `_ContactRow`. |
| `ui/styles.py` | **REESCRITO** — Agora é `get_stylesheet(img_dir)` que injeta o path real do SVG. Cobre todos os componentes. |
| `GeoMetadata_dialog.py` | **ATUALIZADO** — Removido `uic`, `FORM_CLASS`, `setupUi`. Usa `DynamicForm`. Header com `QMenu` dropdown. |
| `img/chevron_down.svg` | **NOVO** — Seta SVG para QComboBox (elimina CSS "pirâmide" dos anos 90). |
| `img/chevron_down_white.svg` | **NOVO** — Variante branca para dark mode. |

#### Arquitetura do `dynamic_form.py`

```
DynamicForm
├── get_scroll_area() → QWidget raiz (FormContainer)
│
├── QTabWidget (#FormTabs)  ← 4 abas estilo web
│   ├── Aba 1: "Identificação"   (_tab_identificacao)
│   │   └── labels acima dos campos, 2 colunas onde faz sentido
│   │
│   ├── Aba 2: "Contato"         (_tab_contato)
│   │   ├── comboBox_contact_presets  (preset CDHU)
│   │   ├── Tabela de contatos estilo GeoNetwork
│   │   │   ├── _primary_row (removable=False) → mapeia FormManager
│   │   │   ├── 2 linhas extras visíveis por padrão
│   │   │   └── [🔍] [+] → _add_contact_row()
│   │   └── Detalhes MGB 2.0 (endereço, telefone, CEP, País)
│   │
│   ├── Aba 3: "Extensão Geográfica" (_tab_extensao)
│   │   └── Norte/Sul e Oeste/Leste em 2 colunas
│   │
│   └── Aba 4: "Metadados"       (_tab_metadados)
│       └── Data de Criação | Data do Metadado + botão Hoje
│
└── FooterBar — label_support_link
```

#### Mapeamento FormManager → DynamicForm
O `FormManager` acessa `self.ui.widget_name`. O `DynamicForm` expõe **exatamente os mesmos atributos**:

| Atributo | Onde está |
|---|---|
| `lineEdit_title`, `textEdit_abstract`, etc. | `_tab_identificacao()` |
| `lineEdit_contact_organisationName` | `_primary_row.field_org` |
| `lineEdit_contact_individualName` | `_primary_row.field_name` |
| `lineEdit_contact_email` | `_primary_row.field_email` |
| `comboBox_contact_role` | `_primary_row.field_role` |
| `comboBox_contact_presets` | `_tab_contato()` |
| `lineEdit_contact_*`, `comboBox_contact_administrativeArea` | `_tab_contato()` (detalhes) |
| `lineEdit_*BoundLatitude/Longitude` | `_tab_extensao()` |
| `dateTimeEdit_*`, `toolButton_set_today` | `_tab_metadados()` |
| `label_support_link`, `label_2` | `_build_footer()` |

#### Header (`GeoMetadata_dialog.py → _create_header`)

```
[Logo CDHU]  [Arquivo ▾]  [Conectividade Geohab ▾]  ........  [ENTRAR]
                │                    │
                ├─ Continuar depois  ├─ Exportar para Geohab  (disabled sem login)
                └─ Exportar .xml     └─ Associar Camada WMS/WFS (disabled sem login)
```

- `_action_salvar`, `_action_exp_xml` → menu Arquivo
- `_action_exp_geo`, `_action_distribution` → menu Geohab (QAction habilitada por `update_ui_for_login_status`)
- `header_btn_login` → QPushButton com ícone ok/error

#### Sistema de Estilos (`ui/styles.py`)

```python
# Uso no dialog:
img_dir = os.path.join(os.path.dirname(__file__), 'img').replace('\\', '/')
self.setStyleSheet(get_stylesheet(img_dir))
```

O `img_dir` é injetado no QSS para que `url({img}/chevron_down.svg)` resolva corretamente em runtime dentro do QGIS (o resource path `:/plugins/...` não é garantido para SVGs em QSS).

**Classes/objectNames chave do QSS:**
- `#FormTabs` → QTabWidget com barra de abas estilo web (linha azul no selecionado)
- `#FieldLabel` → label pequeno acima do campo
- `#ContactColHeader` → cabeçalho das colunas da tabela de contatos
- `#ContactCell` → inputs dentro da tabela de contatos
- `#AddContactButton`, `#RemoveContactButton`, `#SearchButton`
- `#TodayButton` → botão "Hoje" na aba Metadados
- `#HeaderDropdownButton` → QToolButton com QMenu (nav bar)
- `#DropdownMenu` → QMenu estilizado como popover web
- `#ConnectButton` → botão de login
- `#FooterBar`, `#label_support_link`

#### Refinamentos Estéticos e Estruturais — Padrão GeoNetwork (22/04/2026)

**1. Reorganização das Abas:**
- **Aba "Identificação":** Agora é a tela principal "Home", contendo Título, Data, Resumo, Status e toda a seção de **Ponto de Contato**. Segue o fluxo do GeoNetwork onde o usuário resolve o essencial na primeira aba.
- **Aba "Classificação":** Nova aba técnica que absorveu campos como Representação Espacial, Idioma, Categoria e Escala.
- **Aba "Metadados":** Simplificada para conter apenas a Data do Metadado.

**2. Componentes de UI Refinados:**
- **Campo de Data Dinâmico:** Dividido em 3 colunas: `[Tipo ▾]` (Combo), `[Data 📅]` (QDateEdit) e `[Hora 🕐]` (QTimeEdit).
- **Accordion de Endereço:** Implementado `_build_accordion` para a seção "Detalhes de endereço (MGB 2.0)", mantendo o formulário de contato limpo e organizado.
- **Estilo Fusion Universal:** Forçada a aplicação do `QStyleFactory.create("Fusion")` para **todos** os widgets (`QLineEdit`, `QComboBox`, `QSpinBox`, `QDateEdit`, `QTimeEdit`, `QTextEdit`) no Windows, garantindo que o QSS de bordas arredondadas e cores seja respeitado em toda a interface.

**3. Especificações Visuais Finais:**
- **Background:** `#f5f5f5` para inputs (cinza claro moderno).
- **Border-Radius:** 
    - `2px` para `QLineEdit` e `QSpinBox` (estética GeoNetwork tradicional).
    - `8px` para `QComboBox` (~0.5rem).
    - `12px` para `QTextEdit` (Resumo) para manter a suavidade em caixas grandes.
- **Header:** Limpeza de botões redundantes e consolidação nos menus dropdown.

#### Próximos Passos (Roadmap v2.1)
1. **Validação de Abas:** Destacar visualmente (ex: cor vermelha na label da aba) quando houver campos obrigatórios vazios.
2. **Integração MGB 2.0 Multi-contato:** Refinar o `collect_data()` para incluir todos os contatos extras gerados dinamicamente na aba Home.
3. **Persistência de Estados:** Salvar se o accordion de endereço estava aberto/fechado.
4. **Deletar** `GeoMetadata_dialog_base.ui` e arquivos `.py` legados relacionados.

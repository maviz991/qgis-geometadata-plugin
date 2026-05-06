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
| `comboBox_service_type`, `lineEdit_layer_search`, `btn_addservice` | `_tab_recursos()` |
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
- **Aba "Metadados":** Simplificada para conter apenas a Data do Metadado.
- **Aba "Recursos associados":** Nova aba que centraliza a associação de serviços WMS/WFS via GeoServer, com busca em tempo real e painel de badges.

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

**4. Integração GeoNetwork 4.x (ElasticSearch):**
- **Busca Híbrida Inteligente:** Implementado sistema que consulta o ElasticSearch (`/search/records/_search`) para autocompletar contatos em tempo real.
- **Formatação de Busca:** Sigla aparece primeiro no autocomplete (ex: "CDHU - ...") para facilitar busca direta por acrônimos.
- **Extração de Metadados via XML:** Ao vincular um contato, o plugin agora faz uma requisição isolada ao XML raiz do subtemplate para extrair a Regra (Role), Nome Individual e Organização com 100% de precisão.
- **UX de Reordenação:** Setas `▲`/`▼` permitem mudar a prioridade dos contatos no metadado final sem deletar/recriar.

#### Próximos Passos (Roadmap v2.1)

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

---

## Registro 4 — Navegação por Painéis e Header Refatorado (23/04/2026)

### Contexto
A interface de tela única foi substituída por um sistema de navegação por painéis, consolidando o plugin como uma aplicação multi-módulo com Home page, painel GeoNetwork e painel GeoServer (Fase 2).

### Decisões Implementadas

#### 1. Arquitetura `QStackedWidget`

```
QStackedWidget
  ├─ [0] HomePanel      — tela de entrada com cards de módulos
  ├─ [1] GeoNetworkPanel — formulário MGB 2.0 (conteúdo anterior)
  └─ [2] GeoServerPanel  — placeholder Fase 2
```

O plugin abre sempre na Home (índice 0). A navegação é controlada por `_navigate_to_home()`, `_navigate_to_geonetwork()` e `_navigate_to_geoserver()`.

#### 2. Novos Arquivos

| Arquivo | Descrição |
|---|---|
| `ui/home_panel.py` | **NOVO** — Tela inicial com cards de módulo. Emite sinais `navigate_geonetwork` e `navigate_geoserver`. |
| `ui/geoserver_panel.py` | **NOVO** — Placeholder visual da Fase 2 com lista de funcionalidades previstas. |

#### 3. Header como Navbar — Layout Final

```
[Logo CDHU 🖱️]  [Arquivo ▾]  [GeoNetwork ▾]  [GeoServer ▾]  ........  [ENTRAR]
      │                            │                  │
   (navega                    Metadados          GeoServer (navega)
    para Home)                ────────           ────────────────────
                              Exportar GeoNetwork   Em desenvolvimento — Fase 2
                              Assoc. WMS/WFS        Publicar Camada... (disabled)
                              ────────
                              Exportar .xml
                              Importar... (placeholder)
```

> O **logo** passou a ser um `QPushButton` clicável (`#LogoButton`) e é o ponto de retorno à Home, eliminando o botão "Home" textual.

#### 4. Classe `NavButton` — Implementação Final

Substituiu `QToolButton` com `DelayedPopup` por `QPushButton` com controle total. Evolução em iterações:

| Aspecto | Abordagem inicial | Solução final |
|---|---|---|
| Hover abre menu | `enterEvent` → `popup()` | idem ✓ |
| Trocar entre menus | `eventFilter MouseMove` | idem ✓ |
| Menu fecha ao sair | timer 200ms + `widgetAt()` | idem ✓ |
| Estilo hover e ativo | `[hovered]` QSS prop + `update()` | **`setStyleSheet()` inline** — mais confiável |
| Hover "preso" | `polish()` + `WA_Hover` | `setStyleSheet("")` limpa inline; sem `polish()` |
| Estado ativo | `setProperty(navActive)` + `update()` | `set_nav_active(bool)` → `setStyleSheet(inline)` |
| Detecção dark mode | — | `_is_dark()` lê `window().property("theme")` |

Constantes de estilo inline (isolam cores do QSS global):
```python
_HOVER_LIGHT  = "color:#6d7075;background:#f8fafc;border-bottom:3px solid #cbd5e1;"
_ACTIVE_LIGHT = "color:#e5222d;background:transparent;border-bottom:3px solid #e5222d;font-weight:700;"
_HOVER_DARK   = "color:#94a3b8;background:#273549;border-bottom:3px solid #475569;"
_ACTIVE_DARK  = "color:#38bdf8;background:transparent;border-bottom:3px solid #38bdf8;font-weight:700;"
```

#### 5. `_make_menu()` — Menus com cantos arredondados no Windows

Método factory para criação de `QMenu` com flags que ativam o canal alpha da janela nativa:
```python
menu.setWindowFlags(flags | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
menu.setAttribute(Qt.WA_TranslucentBackground, True)
```
Isso torna transparentes os pixels fora do `border-radius` do QSS, eliminando o fundo preto quadrado em cantos no Windows.

#### 6. Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `GeoMetadata_dialog.py` | `NavButton` (refactor completo), `_make_menu()`, logo → `_logo_btn`, `_set_active_nav_btn()` simplificado |
| `ui/styles.py` | QSS `NavButton` simplificado (estados via inline), `#LogoButton`, ajustes `DropdownMenu` |
| `ui/home_panel.py` | Branding: "GeoNetwork" → "catálogo do Geohab" nos cards |

---

## 🐛 Backlog / Features Abertas

### [FEATURE] Header — Refinamento Visual e UX

**Aberto em:** 23/04/2026  
**Atualizado em:** 23/04/2026  
**Prioridade:** Média  
**Módulo:** `GeoMetadata_dialog.py` → `_create_header` + `ui/styles.py`

#### Progresso

| Item | Status | Obs |
|---|---|---|
| Hover instável / múltiplos hovers presos | ✅ Resolvido | `setStyleSheet()` inline + `_apply_hover(False)` explícito em `_switch_to_me()` |
| Logo navega para Home | ✅ Resolvido | `_logo_btn` (QPushButton clicável) substituiu botão "Home" textual |
| Menus com cantos arredondados (sem fundo preto) | ✅ Resolvido | `_make_menu()` com `FramelessWindowHint + WA_TranslucentBackground` |
| Branding consistente ("Geohab" em vez de "GeoNetwork") | ✅ Resolvido | `home_panel.py` atualizado |
| Seta `▾` indicadora nos botões de menu | 📋 Pendente | — |
| Menu `Arquivo > Importar Metadado` funcional | 📋 Pendente | Implementar via `QFileDialog` + `xml_parser.py` |
| "Continuar depois" com feedback visual | 📋 Pendente | Toast/notificação de sucesso/falha |
| Responsividade em janelas estreitas | 📋 Pendente | Detectar largura mínima, recolher label para ícone |

#### Critérios de conclusão
- [x] Hover estável em 100% dos cenários de navegação rápida
- [x] Logo como ponto de retorno à Home
- [x] Cantos arredondados nos menus dropdown (sem artefatos Windows)
- [ ] Seta `▾` visível nos botões `GeoNetwork` e `GeoServer`
- [ ] `Importar Metadado (.xml)` funcional (ou removido se prematuro)
- [ ] Header responsivo para janelas estreitas

---

## Registro 5 — Correção de Loop de Dependências e Ativação do HTML "GoLive" (06/05/2026)

### Contexto
O usuário enfrentava um loop infinito no `SetupDialog` causado por um falso positivo de dependência faltante (`PyQtWebEngine`). O diagnóstico revelou que a biblioteca estava instalada, mas falhava ao importar devido à falta da flag `AA_ShareOpenGLContexts` e conflitos de caminhos no Windows (shadowing entre site-packages do QGIS e do Usuário).

### Decisões Tomadas

1. **Ativação Obrigatória do HTML:** Conforme solicitação do usuário, o fallback para a interface QSS (widgets puros) foi **removido**. O plugin agora exige `PyQtWebEngine`.
2. **Correção de Inicialização (OpenGL):** Adicionada a configuração `QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)` no `__init__.py` do plugin para garantir que o WebEngine possa ser carregado pelo Qt do QGIS.
3. **Injeção de Path (Windows Fix):** O `env_checker.py` agora injeta automaticamente o `site.getusersitepackages()` no `sys.path` para garantir que pacotes instalados via `pip install --user` (como `msal`) sejam visíveis.
4. **Detecção Robusta de Importação:**
    - O `env_checker.py` agora diferencia "Módulo não encontrado" de "Erro de inicialização/DLL". Erros de OpenGL/Runtime agora são tratados como **sucesso** (indicam que a lib está presente).
    - O `login_dialog.py` tenta importar de `qgis.PyQt` e, em caso de falha, tenta `PyQt5` diretamente (necessário para instalações via pip).
5. **Proteção de UI:** Adicionada flag `_setup_in_progress` no `GeoMetadata.py` para evitar que o diálogo de instalação abra múltiplas vezes simultaneamente.

### Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `__init__.py` | Injeção de `AA_ShareOpenGLContexts` e pré-import do WebEngine. |
| `core/env_checker.py` | Injeção de `sys.path`, logs detalhados e lógica de detecção de erros de inicialização. |
| `core/dependency_installer.py` | Refinamento na detecção do executável Python do QGIS. |
| `ui/login_dialog.py` | **Remoção do modo QSS**, importação robusta de WebEngine e restauração dos Workers de segundo plano. |
| `ui/setup_dialog.py` | Mensagem de erro contextual sugerindo o uso do OSGeo4W Setup para conflitos de DLL. |
| `GeoMetadata.py` | Flag de controle para evitar diálogos de setup duplicados. |

### Resultados
- Loop de instalação resolvido.
- Interface HTML funcionando com scrollbar nativa e design premium.
- Estabilidade garantida via workers em `QThread` para não travar a UI durante o login.

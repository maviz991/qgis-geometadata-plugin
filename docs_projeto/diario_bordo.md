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
- [x] Estabilidade garantida via workers em `QThread` para não travar a UI durante o login.

---

## Registro 6 — Refinamento de UX e Estabilização do Ambiente de Instalação (06/05/2026)

### Contexto
Após a ativação da interface HTML, foram identificados pontos de atrito na experiência do usuário, como mensagens excessivamente técnicas, abertura de múltiplos diálogos e a exibição de janelas de terminal ("tela preta") durante a instalação de dependências.

### Decisões Tomadas

1. **Comunicação Humanizada:** 
    - Removidos nomes técnicos (`msal`, `PyQtWebEngine`) das mensagens de interface. 
    - Substituídos por termos amigáveis: "Login corporativo" e "Interface visual nativa".
    - Botão de instalação alterado para "Configurar ambiente de login".
2. **Integração de Suporte (CDA):** 
    - Inclusão de links HTML clicáveis para `https://cda.cdhu.sp.gov.br` em todos os diálogos de erro.
    - Configurado `setOpenExternalLinks(True)` no `SetupDialog` para abertura automática no navegador do sistema.
3. **Instalação Silenciosa (Stealth Mode):** 
    - Implementada a flag `subprocess.CREATE_NO_WINDOW` no `DependencyInstaller`. 
    - Isso suprime a janela de console do Windows durante o `pip install`, mantendo o foco do usuário apenas na barra de progresso do plugin.
4. **Centralização e Travas de UI:** 
    - Criada a trava global `_setup_dialog_open` no `env_checker.py`.
    - Implementada a função `check_and_run_setup()` para garantir que apenas uma instância do diálogo de configuração seja aberta, independente de quem a dispare (timer ou botão de login).

### Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `core/env_checker.py` | Trava global, rótulos amigáveis e função `check_and_run_setup`. |
| `core/dependency_installer.py` | Implementação de `CREATE_NO_WINDOW` para instalação silenciosa. |
| `ui/setup_dialog.py` | Título "Geohab Plugin", links clicáveis e mensagens humanizadas. |
| `ui/templates/login.html` | Mensagens de suporte e link para o CDA integrados. |
| `ui/web_bridge.py` | Mensagens de erro com link HTML para o CDA. |
| `GeoMetadata.py` | Migração para a chamada centralizada de setup. |
| `GeoMetadata_dialog.py` | Migração para a chamada centralizada de setup no botão de login. |

### Resultados
- Experiência de usuário polida e profissional.
- Processo de configuração totalmente em background (sem janelas invasivas).
- Canal de suporte (CDA) acessível diretamente pela interface.

---

## Registro 7 — Estabilização Pós-Migração HTML: form_manager e Bridge (06/05/2026)

### Contexto
Após a migração da UI para HTML (`QWebEngineView`), uma série de `AttributeError: 'GeoMetadataDialog' object has no attribute 'form_manager'` surgiu em tempo de execução. A causa raiz era que o `FormManager` deixou de ser inicializado no `__init__` (conforme planejado — *"será inicializado sob demanda ou vinculado à bridge"*), mas vários métodos do diálogo ainda o referenciavam diretamente, sem guard.

Além disso, a home não carregava: dois bugs no `app.js` impediam a inicialização da interface HTML.

### Problemas Identificados e Corrigidos

#### 1. `form_manager` ausente — 8 pontos de crash

| Método | Linha | Fix |
|---|---|---|
| `authenticate()` | 662 | Removida chamada `populate_comboboxes()` — comboboxes agora são JS |
| `closeEvent()` | 1191 | Guard `hasattr` → fecha sem prompt se `form_manager` ausente |
| `exportar_to_xml()` | 675–677 | Guard no topo → exibe "Em desenvolvimento" e retorna |
| `exportar_to_geo()` | 698–703 | Guard no topo → exibe "Em desenvolvimento" e retorna |
| `save_metadata()` | 726–728 | Guard no topo → retorna silenciosamente |
| `auto_fill_from_layer()` | 755–756 | Guard na condição → pula preenchimento |
| `_update_offline_contacts()` | 1012 | `self.form_manager.contatos_predefinidos` → `self.contatos_predefinidos` |
| `_fetch_contacts_online()` | 1070 | idem |
| bloco contato primário | 1147 | Guard duplo: `self.ui` e `self.form_manager` ausentes → `return` |

**Regra:** `contatos_predefinidos` já existe em `self` (carregado em `_load_contacts()`), não precisa de `form_manager`.

#### 2. Home não carregava — dois bugs no `app.js`

**Bug A — `fetch()` bloqueado por segurança do QWebEngine:**
`fetch('panels/home.html')` falha silenciosamente em contexto `file://`. O Chromium embarcado bloqueia requisições `fetch` entre origens `file://` por padrão.

**Solução:** Novo slot `bridge.load_panel_html(panelId, callback)` em `main_bridge.py`. Python lê o arquivo com `open()` e devolve a string via QWebChannel. Zero dependência de políticas do browser.

**Bug B — `await bridge.get_initial_data()` retornava `undefined`:**
QWebChannel **não retorna Promises**. `await slot()` resolve imediatamente como `undefined`, quebrando o acesso a `data.is_logged` com TypeError.

**Solução:** Reescrito o padrão de chamada para callback explícito:
```javascript
// ERRADO (antes)
const data = await bridge.get_initial_data();

// CORRETO (depois)
bridge.get_initial_data(function(data) { ... });
```
O mesmo padrão foi aplicado a `load_panel_html`.

### Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `GeoMetadata_dialog.py` | Guards `hasattr` em todos os 8 pontos de crash do `form_manager` |
| `ui/main_bridge.py` | Novo slot `load_panel_html(panel_id) -> str` |
| `ui/templates/js/app.js` | Substituição de `fetch` + `async/await` por callbacks QWebChannel |

### Regra de Ouro para Futuros Slots com Retorno

Todo slot Python que retorna valor **deve ser chamado com callback no JS**:
```javascript
bridge.meu_slot(arg, function(resultado) {
    // usar resultado aqui
});
```
Nunca usar `await bridge.meu_slot()` — QWebChannel não é Promise-based.

---

## Registro 8 — Formulário Completo de Metadados (HTML) (06/05/2026)

### O que foi feito
Migração do formulário MGB 2.0 do PyQt (`DynamicForm` + `FormManager`) para HTML puro no painel `editor.html`.

### Arquivos modificados

| Arquivo | Mudança |
|---|---|
| `ui/templates/panels/editor.html` | Formulário completo com 4 abas e todos os campos |
| `ui/templates/js/app.js` | `showTab`, `collectFormData`, `validateForm`, `populateForm`, `tryExport*` |
| `ui/templates/main.html` | Botões de ação chamam `tryExportXml/Geohab/Save()` em vez do bridge direto |
| `ui/main_bridge.py` | `export_xml`, `export_geohab`, `save_metadata` recebem `QVariant` (dict do form) |
| `GeoMetadata_dialog.py` | Os três métodos aceitam `metadata_dict=None`; novo helper `_normalize_dates()` |

### Abas do formulário

| Aba | Campos |
|---|---|
| Identificação | Título\*, Edição, Resumo\*, Palavras-chave\*, Escala, Thumbnail URL |
| Classificação | Status\*, Tipo Espacial\*, Categoria Temática\*, Nível Hierárquico\*, Idioma\*, Charset |
| Extensão | BBox N/S/L/O\*, Data do metadado, Data de criação |
| Contato | Sigla\*, Organização\*, Cargo, Tel., E-mail\*, Responsabilidade\*, Endereço\*, Cidade\*, Estado\*, CEP\*, País\* |

### Fluxo de exportação
1. Usuário clica "Exportar .xml" ou "Publicar no Catálogo" no header
2. `tryExportXml()` / `tryExportGeohab()` chama `collectFormData()` → dict JS
3. `validateForm()` verifica campos obrigatórios; marca borda vermelha nos inválidos
4. Se válido: `bridge.export_xml(data)` / `bridge.export_geohab(data)`
5. Python recebe o dict, normaliza datas (`HH:MM` → `HH:MM:00Z`) e gera o XML

### Compatibilidade com legado
`exportar_to_xml(metadata_dict=None)` — se `None`, cai no `form_manager` PyQt (caso ainda exista). Se vier dict do JS, usa diretamente. Sem quebra de compatibilidade.

---

## Registro 9 — Auditoria: Código vs. Documentação (07/07/2026)

### Contexto
Levantamento no código (branch `dev-v_1.0.4-html`) para verificar o que estava efetivamente implementado versus o que os registros anteriores deste diário descreviam. Duas divergências relevantes foram encontradas.

### Divergências Encontradas

1. **`geoserver_publisher.py` nunca foi criado.** O Registro 2 (17/04/2026) descrevia essa classe como módulo centralizado para a REST API do GeoServer — ela não existe no repositório. O que existe é `ui/geoserver_panel.py`, um placeholder visual de ~4KB (`__init__`, `_build_ui`, `_build_card`) com docstring explícito de "Fase 2", sem nenhuma lógica de publicação. Além disso, `_create_geoserver_panel()` (e `_create_geonetwork_panel()`) em `GeoMetadata_dialog.py` **não são chamados em nenhum lugar** — junto com `ui/dynamic_form.py` e `ui/form_manager.py`, é código PyQt legado órfão, não removido conforme previsto no Roadmap v2.1 ("Deletar `GeoMetadata_dialog_base.ui` e arquivos `.py` legados relacionados" — apenas o `.ui` foi de fato removido).
2. **Versão ainda é `1.0.1`.** `metadata.txt` não reflete a label "2.0.0 dev" usada neste diário desde o cabeçalho ("Estado Atual do Plugin"). Não há string `2.0.0` em nenhum arquivo versionado (`__init__.py`, `GeoMetadata.py`, `metadata.txt`).

### O que foi confirmado como correto
Auth via Entra ID/MSAL (`core/entra_auth_provider.py`), UI HTML/QWebEngine como caminho real do construtor, e todo o trabalho de formulário de contatos (validação CEP/telefone, accordion, dedup, `geometadata_user_contacts.json`) — todos batem com o código atual.

### Nota
Limpeza dos arquivos órfãos (`dynamic_form.py`, `form_manager.py`, `geoserver_panel.py` e scratch files soltos na raiz como `patch*.py`, `temp.py`) foi identificada mas adiada — não faz parte deste registro.

---

## Registro 10 — Correção dos Bugs de Persistência e Publicação GN (07/07/2026)

### Contexto
Ver `docs_projeto/bugs.md` (registro "conexão", 07/07/2026) para os tracebacks originais.

### Bugs Corrigidos

1. **Crash ao mostrar erro de salvamento no DB.** `core/persistence_service.py:_show_message` usava `QtWidgets.QMessageBox.RichText`, que não existe (é `Qt.TextFormat`, não `QMessageBox`) — o `AttributeError` mascarava o erro real (`psycopg2.errors.UndefinedTable`, tabela `public.qgis_geometadata_plugin` ausente no banco de destino). Corrigido para `QtCore.Qt.RichText`. Adicionado `except psycopg2.errors.UndefinedTable` específico que orienta o usuário a abrir ticket no CDA solicitando a criação da tabela, em vez de mostrar o erro cru.
2. **Sessão da API congelada no `MetadataService`.** `self.metadata_service = MetadataService(self.plugin.api_session)` capturava o valor da sessão na construção do diálogo (`GeoMetadata_dialog.py:270`), sempre antes do login acontecer. Login via SSO/admin (`ui/main_bridge.py`) atualiza `self.plugin.api_session`, mas o `MetadataService` nunca via essa atualização — resultando em "Sessão da API não foi inicializada" mesmo logado. Fix: `MetadataService` agora guarda referência ao `plugin` e lê `self.plugin.api_session` em tempo real dentro de `push_to_geonetwork`.
3. **400 Bad Request ao republicar metadado com UUID já existente no GN.** Após o fix do item 2, publicar um metadado cujo `fileIdentifier` já existia no GN (ex.: importado manualmente durante o período em que o login estava quebrado) retornava 400, pois `PUT /srv/api/records` sem `uuidProcessing` usa o default `NOTHING` (rejeita duplicado). Fix: adicionado `uuidProcessing=OVERWRITE` na chamada. Também foi ligado o `translate_http_error` (existia em `metadata_service.py` mas nunca era chamado) ao tratamento de erro, para que um 400 residual de UUID duplicado apareça como mensagem amigável em vez do erro HTTP cru.

### Em aberto
Registro "metadado GN - online" (`docs_projeto/bugs.md`) segue sem solução: (1) contatos não sendo gravados corretamente no XML gerado (cai no fallback CDHU mesmo com contato do catálogo selecionado) e (2) elementos (recursos WMS/WFS, contatos) somem ao reprocessar o metadado pelo GN — suspeita de comportamento de subtemplate da registry do GN quando o `xlink:href` gerado não corresponde a uma entrada já registrada.

---

## Registro 11 — Causa Raiz do Contato "Sumido" e Fix de Perfil MGB 2.0 (07/07/2026)

### Contexto
Investigação dos dois bugs em aberto do Registro 10, comparando o template MGB 2.0 instalado no GN (`scratch/template_mgb_2_0.xml`) com o XML que o plugin gera hoje (`scratch/TJ_teste-gn.xml`).

### Causa Raiz Confirmada
`_build_contact_block()` (`core/xml_generator.py`) envolvia todo `gmd:contact`/`gmd:pointOfContact`/`gmd:processor` num `xlink:href="local://srv/api/registries/entries/{uuid}"` — padrão de referência a subtemplate da registry do GN, deixando a tag auto-fechada sem nenhum dado embutido. O `uuid` usado era **sempre gerado aleatoriamente** (`contact_data.get('uuid') or uuid4()`), porque o JS (`ui/templates/js/app.js`) nunca envia uma chave `uuid` — só `_gn_uuid`, usado apenas para o enriquecimento local dos campos, nunca repassado ao gerador de XML. Resultado: a referência nunca correspondia a uma entrada real da registry do GN, que não conseguia resolver nada — daí o contato "sumir" e, junto com ele, potencialmente outros elementos dependentes.

O template MGB 2.0 instalado no GN não usa esse padrão — embute `CI_ResponsibleParty` diretamente dentro de `gmd:contact`/`gmd:pointOfContact`, sem `xlink:href` e sem `uuid`.

Também identificado: `metadataStandardName`/`metadataStandardVersion` estavam hardcoded como `ISO 19115` / `2003/Cor.1:2006` (perfil ISO 19139 genérico), enquanto o template instalado declara `ISO 19115-3:2014` / `MGB 2.0`.

### Fix Aplicado (v1)
- `_build_contact_block()`: removido o wrapper `xlink:href`; `CI_ResponsibleParty` agora é sempre embutido diretamente, igual ao template.
- `generate_xml()`: `metadataStandardName` → `ISO 19115-3:2014`, `metadataStandardVersion` → `MGB 2.0`.

### Teste e Correção do Fix (mesmo dia)
Testado: ponto de contato passou a aparecer, mas o contato de metadado (`gmd:contact`) não aparecia no **modo de edição** do GN (só no modo de leitura), e os contatos apareciam como "manual" em vez de vinculados ao diretório.

Comparando com `scratch/t-exemplo.xml` (registro real de produção, funcionando 100%), o padrão correto do GN **usa sim `xlink:href`**, mas com o **uuid real** da entrada na registry — não um uuid inventado. O uuid `b98c4847-4d5c-43e1-a5eb-bd0228f6903a` usado no exemplo de produção é exatamente o mesmo já cadastrado no preset `"cdhu"` de `assets/contacts.json` (e os outros presets — DPDU, SSARU, TERRAS, SPHU — também têm seus próprios uuids reais nesse arquivo). O fix v1 removeu o `xlink:href` por completo, o que resolvia o caso de uuid inventado mas quebrava o vínculo com o diretório para os presets institucionais, que sempre tiveram um uuid real disponível.

**Fix v2 (correto)**: `_build_contact_block()` volta a emitir `xlink:href` + `CI_ResponsibleParty uuid="..."`, mas só quando existe um uuid real disponível em `contact_data.get('uuid')` (presets do `contacts.json`) ou `contact_data.get('_gn_uuid')` (contato escolhido via busca no catálogo GN). Sem uuid real — contato puramente manual, nunca cadastrado na registry — embute só o `CI_ResponsibleParty`, sem inventar uuid nem gerar link quebrado.

### Teste v2 e Correção Final (mesmo dia)
Com o v2 (após recarregar o plugin no QGIS — o teste anterior tinha rodado com o módulo Python antigo ainda em cache), o ponto de contato do recurso passou a aparecer corretamente vinculado ao diretório em modo de edição. A duplicação de CDHU+TERRAS em `gmd:contact` (metadado) e `gmd:pointOfContact` (recurso) é intencional — o usuário adicionou os dois contatos em ambas as seções da UI.

Porém: o painel "Autor dos metadados" do editor do GN (aba Metadados) continuava vazio em modo de edição, mesmo com o dado presente no XML (visível só em modo de leitura). Comparando com o `gmd:contact` de `scratch/t-exemplo.xml` (produção, funcionando 100%): lá o role é `author`. No nosso XML o role do `gmd:contact` saía como `owner`/`pointOfContact` — herdado do papel que o mesmo contato tem na tabela de **recurso**, porque `_build_contact_block` usa o campo `role` do próprio contato sem diferenciar o contexto. O widget "Autor dos metadados" do GN não expõe seletor de Regra (só busca + "+"), ou seja, só reconhece um contato ali quando o role é `author`.

**Fix v3**: em `generate_xml()`, o role é forçado para `'author'` especificamente para os contatos que vão em `gmd:contact` (tanto de `metadataAuthorContacts` quanto o fallback CDHU), independente do role que o contato tem na tabela de recurso.

### Teste v3 — Hipótese Descartada e Fix Revertido (mesmo dia)
Usuário testou manualmente definindo 2 contatos (CDHU e DPDU) com role `author` diretamente na UI. O XML gerado saiu com `role="author"` corretamente em ambos os `gmd:contact` (com `xlink:href` + uuid real) — e mesmo assim "Autor dos metadados" continuou vazio no modo de edição do GN. **A hipótese do role="author" foi descartada.**

Feedback do usuário: o gerador de XML não deve forçar/alterar o role arbitrariamente — deve refletir exatamente o que está nos dados do contato, sem inventar valor por hipótese. O fix v3 foi **revertido** em `core/xml_generator.py` (`_build_contact_block` volta a usar o role que vem do próprio contato).

### Em Aberto
"Autor dos metadados" não aparece em modo de edição no GN mesmo com uuid real e role correto no `gmd:contact` — causa raiz ainda não identificada. Possivelmente está fora do escopo do `xml_generator.py`: pode ser uma condição específica do config-editor do perfil MGB2.0 no GN (schema binding daquele campo específico) que exigiria investigação do lado do GN, não do plugin. Pendente: comparar mais a fundo com `scratch/t-exemplo.xml` (ordem de elementos, atributos extras não replicados) antes de tentar outra hipótese.

---

## Registro 12 — Elemento Estrutural Inválido no XML (`hierarchyLevelName`) (07/07/2026)

### Contexto
Continuação da investigação do Registro 11 ("Autor dos metadados" vazio). Ver `docs_projeto/bugs.md` (registro "metadado GN - online", Bug 3) para o achado completo. Comparação de três arquivos de referência: `scratch/template_mgb_2_0.xml` (template MGB 2.0 instalado no GN), `scratch/t-exemplo.xml` (registro real de produção, funcionando) e `scratch/TJ_teste-gn.xml` (saída atual do plugin).

### Causa Raiz Confirmada
`generate_xml()` em `core/xml_generator.py` gerava um elemento `gmd:hierarchyLevelName` com `gco:CharacterString` **duplicado/aninhado** — `<gco:CharacterString><gco:CharacterString>dataset</gco:CharacterString></gco:CharacterString>` — inválido contra o XSD ISO19139, já que `gco:CharacterString` é um tipo string simples e não pode conter outro `gco:CharacterString` como filho. Nem o template instalado nem o registro de produção usam esse elemento — o plugin estava inserindo um campo fora do perfil MGB 2.0, além de malformado.

### Fix Aplicado
Removida a linha `_char(_sub(root, 'gmd', 'hierarchyLevelName'), 'gco', 'CharacterString', hier)` em `core/xml_generator.py` (bloco `hierarchyLevel` de `generate_xml()`). Verificado com teste local (`generate_xml()` chamado direto em Python) que o elemento não aparece mais na saída.

### Hipótese em Aberto
Elemento inválido no XML pode estar contribuindo para falhas mais amplas de data-binding no editor MGB2.0 do GN — não necessariamente restrito ao campo de contato investigado nos Registros 10-11. Aguardando teste do usuário no GN (após reload do plugin) para confirmar se o painel "Autor dos metadados" passa a aparecer corretamente em modo de edição.

---

## Registro 13 — Seletor de Processamento de UUID, Sistema de Toast e Fix do enum `uuidProcessing` (07-08/07/2026)

### Contexto
GeoNetwork expõe 3 estratégias na publicação de um metadado com UUID já existente ("Processamento de identificador de registro": Nenhum / Sobrescrever / Gerar UUID novo). Até aqui o plugin forçava `uuidProcessing=OVERWRITE` sempre, sem o usuário poder escolher. Pedido do usuário: replicar essa escolha no plugin.

### Implementação Inicial (QDialog nativo)
Primeira versão (`_ask_uuid_processing()` em `GeoMetadata_dialog.py`) usou um `QDialog`/`QRadioButton` nativo do Qt antes de chamar `push_to_geonetwork()`. Funcionalmente correto, mas visualmente destoante — janela nua do Windows no meio de uma UI 100% HTML/CSS.

### Bug: enum `uuidProcessing` errado
Ao testar com a opção "Nenhum", GN devolveu erro cru do Spring: `Failed to convert value of type 'java.lang.String' to required type '...MEFLib$UuidAction'`. Causa: o valor enviado pro parâmetro era `'NONE'`, mas o enum Java real (`MEFLib$UuidAction`) só aceita `NOTHING`, `OVERWRITE`, `GENERATEUUID` — não existe `NONE`. Fix: trocado `'NONE'` → `'NOTHING'` em `core/metadata_service.py` (default de `push_to_geonetwork`) e no seletor, mantendo o label "Nenhum" na UI (só o valor da API mudou).

De quebra, achado outro bug de tradução: `translate_http_error()` tinha a chave `"already exists"` (com "s"), mas a mensagem real do GN pra UUID duplicado diz `"already exist and you choose no action..."` (sem "s") — o `in` nunca batia, e o erro aparecia cru pro usuário. Chave trocada para `"already exist"` (substring que casa com ambos os casos) e o texto atualizado pra orientar o uso do seletor de UUID em vez da instrução antiga ("delete o registro").

### Sistema de Toast (padrão visual HTML/CSS)
Tarefa acoplada, já pendente desde o Registro 4 (backlog "Toast/notificação de sucesso/falha"). Antes de implementar, auditamos todos os `QMessageBox` do repositório e confirmamos que boa parte estava em código morto (`form_manager.py`, `unified_login_dialog.py`, e métodos legados em `GeoMetadata_dialog.py` que dependem de `self.ui`/`self.form_manager`, nunca instanciados na UI HTML atual — consistente com a auditoria do Registro 9). Escopo final ficou restrito aos caminhos vivos, todos disparados via `main_bridge.py`: exportar XML, publicar no GN, salvar (DB/sidecar).

Implementação:
- `ui/main_bridge.py`: novo sinal `toast = pyqtSignal(str, str, str)` (message, title, type).
- `ui/templates/js/app.js`: `bridge.toast.connect(...)` chama `Modal.alert(message, title, type)` — reaproveita o sistema de modal HTML/CSS já existente (`modals.js`/`modals.css`), o mesmo usado pelas validações client-side.
- `GeoMetadata_dialog.py`: novo método `show_toast(title, message, msg_type)` que emite o sinal da bridge; cai automaticamente no `show_message()` nativo antigo se a bridge ainda não existir (único caso real: erro ao carregar `assets/contacts.json` no `__init__`, antes da webview carregar).
- `core/persistence_service.py`: `_show_message()` tenta `parent_widget.show_toast(...)` primeiro, com o mesmo fallback nativo — parâmetro `icon=QMessageBox.X` trocado por `msg_type='error'/'warning'/'success'/'info'` em todos os call sites.
- Confirmações com decisão (Ok/Cancel que ramificam o fluxo Python) ficaram fora do escopo do toast de propósito — não dá pra bloquear/ramificar de forma limpa com um toast assíncrono sem reescrever o fluxo todo.

### Fix Final: Seletor de UUID Também Migrado pro HTML
Usuário sinalizou (com print) que o seletor de UUID ainda aparecia como diálogo nativo do Windows — exatamente o problema descrito acima, fora do escopo inicial do toast por ser uma confirmação com decisão. Resolvido migrando esse caso específico também:
- `ui/templates/js/modals.js`: novo `Modal.confirmOptions()` — confirmação genérica com N opções em radio button, reaproveitável.
- `ui/templates/css/modals.css`: estilos `.modal-radio-group`/`.modal-radio-option` no padrão visual do projeto (tokens `--border`, `--accent`, `--fg-muted`).
- `ui/templates/js/app.js`: `tryExportGeohab()` agora chama `Modal.confirmOptions(...)` com as 3 opções antes de `bridge.export_geohab(data)`; a escolha viaja em `data.uuidProcessing`.
- `GeoMetadata_dialog.py`: removido `_ask_uuid_processing()` (QDialog nativo) e o import órfão de `QDialog`. `exportar_to_geo()` agora só lê `metadata_dict.pop('uuidProcessing', None) or 'NOTHING'` — decisão já vem pronta do JS.

### Bug 5 Resolvido: UUID Errado na Mensagem de Sucesso
Confirmado com log de diagnóstico temporário (`print` do JSON bruto de resposta, removido depois): a resposta do `PUT /srv/api/records` (`SimpleMetadataProcessingReport`) tem sim um campo `uuid` na raiz, mas é o **id do job de processamento**, não o uuid do metadado publicado — por isso a mensagem de sucesso mostrava um valor diferente a cada publicação, mesmo com o GN indexando/sobrescrevendo o registro certo por baixo dos panos. O uuid real fica em `metadataInfos` (mapa id-interno → lista de infos, cada uma com seu próprio campo `uuid`).

Fix em `core/metadata_service.py` (`push_to_geonetwork`): passou a extrair o uuid do primeiro entry de `metadataInfos` em vez do campo `uuid` da raiz. Verificado com a resposta real capturada do GN.

Pedido extra do usuário: mensagem de sucesso agora inclui um link "Acesse aqui" pro registro publicado (`config_loader.get_metadata_view_url(uuid_criado)`, método que já existia em `core/plugin_config.py` — monta a URL a partir do `geonetwork_url` do config, nada hardcoded), no mesmo padrão `target="_blank"` do link do CDA já usado no rodapé (`main.html`).

---

## Registro 14 — Links Externos, Centralização da URL do CDA e Crash Nativo do lxml (08/07/2026)

### Contexto
Sequência de três ajustes menores, todos no mesmo dia, decorrentes do trabalho do Registro 13 (toast/seletor de UUID) e de um crash reportado pelo usuário ao salvar no banco.

### 1. Links Abrindo Dentro do QGIS em Vez do Navegador
Usuário notou que o link "Acesse aqui" do toast de publicação (e outros, como o CDA no rodapé) só abriam no navegador padrão com Ctrl+clique — clique normal navegava dentro do próprio QtWebEngine embutido no QGIS.

**Causa**: links com `target="_blank"` não passam por `acceptNavigationRequest()` (que já tínhamos, cobrindo só clique direto em links sem esse atributo) — o Qt delega pra `createWindow()`, que não estava implementado.

**Fix**: nova classe `_ExternalLinkPage(QWebEnginePage)` em `GeoMetadata_dialog.py`:
- `acceptNavigationRequest()`: se for clique em link (`NavigationTypeLinkClicked`) com esquema `http`/`https`, abre via `QDesktopServices.openUrl()` e bloqueia a navegação interna. Links `file://` (usados pela navegação por `href="#"` do próprio SPA — "Editor de Metadado", "Publicar Metadado" etc.) passam direto, sem interferência.
- `createWindow()`: cria uma `QWebEnginePage` descartável, escuta `urlChanged` (dispara quando o Qt define a URL de destino do `target="_blank"`), abre externamente e destrói a página fantasma — sem popup real.
- Conectado via `self.web_view.setPage(_ExternalLinkPage(self.web_view))`, antes do `QWebChannel`. Cobre todos os links do plugin de uma vez.

### 2. Centralização da URL do CDA
Pedido do usuário: a URL do CDA (`https://cda.cdhu.sp.gov.br/marketplace/formcreator/front/formdisplay.php?id=36`) estava hardcoded em 4 lugares diferentes (`core/persistence_service.py`, `ui/setup_dialog.py` ×2, `ui/web_bridge.py`, `ui/templates/main.html`). Centralizada em `assets/config.json` (chave `cda_url`) + `config_loader.get_cda_url()`. O link do rodapé em `main.html` (HTML estático) agora é preenchido em runtime via JS, lendo `data.cda_url` do retorno de `bridge.get_initial_data()` — variável global `CDA_URL` em `app.js`, reaproveitável por outros pontos do JS no futuro.

Deixados de fora, de propósito (código morto confirmado nas auditorias anteriores, não referenciado por nenhum `.py` do plugin): `ui/templates/login.html` (usado só pelo `LoginDialog` nativo nunca conectado), `Guide_user.html`, `user_guide.html`, `editando.html`.

### 3. Crash Nativo "Windows fatal exception: access violation" ao Salvar
Usuário reportou crash do QGIS inteiro (não uma exceção Python capturável) ao salvar metadado no banco. Traceback apontava pra `xml_generator.py:145`, dentro de `ET.Element(...)` — literalmente a criação do elemento raiz do XML. Reabrir o QGIS resolveu, indicando comportamento intermitente (race condition), não bug determinístico de lógica.

**Investigação**: o stack trace nativo mostrava o crash dentro de `xmlDictReference` (função interna do libxml2, usada por trás do `lxml`) ao tentar entrar numa critical section do Windows — sinal de corrupção de memória por concorrência. Verificação descartou threads do próprio plugin: nenhuma `QThread` em background usa `lxml` (a única que parseia XML de contato do GN, `_GnContactEnrichWorker` em `web_bridge.py`, usa regex puro, não lxml). Busca na web confirmou: é um bug conhecido e já documentado — [qgis/QGIS#58205](https://github.com/qgis/QGIS/issues/58205) — um bug de empacotamento do wheel Windows do **lxml 5.2.1** especificamente, corrigido na 5.2.2+. Confirmado no disco do usuário: `C:\Program Files\QGIS 3.34.12\apps\Python312\Lib\site-packages\lxml-5.2.1.dist-info` — a versão exata afetada.

**Fix**: em vez de expor isso como mais um item na `SetupDialog` (visível, com label amigável, como `msal`/`PyQtWebEngine`), o usuário pediu correção silenciosa. Implementado:
- `core/dependency_installer.py`: `DependencyInstaller` ganhou parâmetro opcional `extra_args` (lista de flags extras pro `pip install`), sem alterar o comportamento dos usos existentes.
- `core/env_checker.py`: `is_lxml_safe()` compara a versão instalada contra `(5, 2, 2)`; `silently_fix_lxml_if_needed()` dispara `pip install --user --upgrade "lxml>=5.2.2"` em background via `DependencyInstaller`, sem diálogo, uma vez por sessão do QGIS (referência à `QThread` mantida num global do módulo pra não ser coletada pelo GC no meio da execução).
- `GeoMetadata_dialog.py`: chamado no `__init__`, junto com `_load_contacts()`.

**Limitação conhecida**: por ser um módulo nativo (`.pyd`) já carregado em memória na sessão atual do QGIS, o upgrade baixado só passa a valer depois que o usuário **reiniciar o QGIS** — não elimina o risco de crash na sessão corrente em que o fix é aplicado.

---

## Registro 15 — Reset, Importar Metadado, Pull do GeoNetwork e Badge de Sincronização (08/07/2026)

### Contexto
Pedido do usuário pra resolver um gap do sistema de draft (editar por teste e não conseguir voltar ao último save nem limpar o form) integrado a três funcionalidades novas relacionadas: importar XML local, puxar metadado do GeoNetwork (busca manual + sincronização automática) e um badge de status por registro. Planejado via `EnterPlanMode` com pesquisa prévia do código (draft/dirty mechanism, endpoints de busca do GN já usados pra contatos, `xml_parser.py`) e duas rodadas de `AskUserQuestion` pra decidir o fluxo do pull e a posição do badge.

### Implementação (plano aprovado)
1. **Descartar Alterações**: novo item no menu "Arquivo", usa `bridge.clear_draft()` (já existia, nunca era chamado por nenhum JS).
2. **Importar Metadado (.xml)**: `QFileDialog.getOpenFileName` (padrão inédito no plugin) + slot `import_xml_file()` em `ui/main_bridge.py`.
3. **Puxar do Geohab (busca manual)**: badge "Offline" clicável abre busca por título, reaproveitando o Elasticsearch já usado pra contatos (`_GnContactsWorker`) mas com `isTemplate: "n"` (registros, não subtemplates) — novo `_GnRecordSearchWorker` em `ui/web_bridge.py`. Escolher um resultado busca o XML completo via `{records_url}/{uuid}/formatters/xml` (mesmo endpoint já validado por `_GnContactEnrichWorker`) — novo `MetadataService.fetch_from_geonetwork()`.
4. **Sincronização automática + badge**: ao carregar uma camada com `metadata_uuid` conhecido, `check_gn_sync()` compara `dateStamp` local vs. GN em background; se o GN tiver uma versão mais nova, badge vira "Atualização disponível" com banner não-bloqueante ("Atualizar agora") — nunca sobrescreve sozinho.

Dependência resolvida antes: `xml_parser.py` não extraía `gmd:dateStamp` — adicionado.

Arquivos: `core/xml_parser.py`, `core/metadata_service.py`, `ui/web_bridge.py`, `ui/main_bridge.py`, `ui/templates/main.html`, `ui/templates/panels/editor.html`, `ui/templates/js/app.js`, `ui/templates/css/{styles,modals}.css`, `GeoMetadata_dialog.py` (removido `_action_import_metadata`, `QAction` morto nunca ligado ao menu HTML vivo).

### Bugs encontrados testando a implementação (mesmo dia)

**Bug 9 — `ValueError: Unicode strings with encoding declaration are not supported`**: `lxml` recusa parsear uma `str` Python com `<?xml ... encoding="UTF-8"?>` (só aceita `bytes` nesse caso). Praticamente todo XML MGB 2.0 real tem essa declaração. Fix na raiz em `core/xml_parser.py` (`parse_xml_to_dict`): converte `str` pra bytes antes de `ET.fromstring()`. Vale pra todo mundo que chama a função, não só as features novas.

**Bug 7 — estado de sincronização/draft sempre "volta ao inicial" ao trocar de camada**. Duas causas raiz:
- **Chave errada**: `xml_parser.py` gera `metadata_uuid`; o campo do form (`f-metadataId`) e `collectFormData()` usam `metadataId`. Dado puxado do GN/importado nunca preenchia o UUID real do form. Fix: `populateForm()` prioriza `data.metadata_uuid`; `collectFormData()` emite `metadata_uuid` como alias.
- **A causa de verdade, mais grave**: `geometadata_form_draft.json` nunca foi um arquivo *por camada* — é um slot único com uma tag `__layer_key__`. Qualquer save enquanto outra camada está ativa sobrescreve o draft inteiro, destruindo o da camada anterior. Usuário documentou o sintoma em detalhe (`docs_projeto/bugs.md` Bug 7) — explicava exatamente por que "Não encontrado no GN"/edições incompletas somem ao trocar de camada e voltar. Fix: `save_draft`/`load_draft`/`clear_draft` em `ui/main_bridge.py` reescritos pra um dict `{chave_da_camada: dados}`, com migração automática do formato antigo. Complementado com: (a) pull do GN e import local salvando na hora (`_saveDraftNow()`, sem o debounce de 1.5s) pra fechar a janela de corrida numa troca de camada rápida; (b) removido um atalho `!_isLogged` redundante em `checkGnSync()` (JS) que podia mostrar "Offline" com sessão válida por causa de um cache desatualizado — `check_gn_sync` do lado Python já verifica a sessão ao vivo.

**Bug 8 — parser não preenchia todos os campos**: `xml_parser.py` só recuperava campos simples e **um** contato — não lia `gmd:pointOfContact`/`gmd:contact`/`gmd:processor` como as listas que `populateForm()` espera, nem `purpose`/`credit`/linhagem, nem `onlineResources` completo. Fix: novo `_parse_responsible_party()`/`_parse_responsible_party_list()` + extração dos campos faltantes, espelhando a estrutura que `xml_generator.py` escreve. Validado com round-trip completo (`generate_xml` → `parse_xml_to_dict`).

**Ruído de console**: `_load_from_db` (agora chamado a cada abertura de camada por causa do `check_gn_sync` automático) imprimia o traceback completo de `psycopg2.errors.UndefinedTable` toda vez — mesma causa do Bug 1, só que no caminho de leitura. Silenciado especificamente esse caso em `core/persistence_service.py`, sem mudar o comportamento (retorna `None`).

### Bug 10 — Modelo de Estados do Badge de Sincronização (mesmo dia)

Testando ainda mais a fundo, o usuário achou três problemas no ciclo de vida do badge: (1) publicar no GN não atualizava o badge pra "Sincronizado" — só no próximo carregamento da camada; (2) esse próximo carregamento mostrava "Atualização disponível" (falso positivo), mesmo sendo a própria publicação recém-feita; (3) não existia um estado pra "editei algo localmente depois de sincronizar, mas ainda não publiquei".

**Causa (1)+(2)**: `exportar_to_geo()` nunca avisava o JS que a publicação tinha dado certo (só o toast genérico) — o badge só reagia no próximo `checkGnSync()`, que compara `dateStamp`. E esse `dateStamp` salvo localmente era o que estava no formulário *antes* de publicar, não o que o GN carimba ao processar (sempre mais novo) — a checagem seguinte sempre concluía "o GN tem algo mais novo", mesmo sendo nossa própria publicação.

**Causa (3)**: não existia rastreamento de "modificado desde a última sincronização" — só a comparação de `dateStamp` contra o GN, que não captura edição local ainda não publicada.

**Modelo adotado** (proposto pelo usuário, inspirado no fluxo git):
- **Sincronizado** — UI/salvo local bate com o GN.
- **Modificado** — estava sincronizado, mas o usuário alterou algo sem publicar (equivalente a "unstaged changes").
- **Não encontrado no GN** (untracked) — salvo local/banco com um uuid que não existe no GN.
- **Offline** — nada salvo ainda, só estado de UI/sessão — estado inicial.

**Fix**:
- Novo sinal `gn_publish_succeeded(uuid)` em `ui/main_bridge.py`, emitido por `exportar_to_geo()` (`GeoMetadata_dialog.py`) logo após publicar com sucesso — que também busca de volta o `dateStamp` real do GN (`fetch_from_geonetwork`) antes de salvar localmente, eliminando a causa do falso "atualização disponível".
- No JS, esse sinal seta o badge direto pra "Sincronizado" e limpa o draft (o save no DB/sidecar já é a fonte da verdade a partir daí).
- Estado "Modificado": flag `_gnSyncClean` (setada em `setGnBadge` sempre que o estado vira `synced`) + listener de `input`/`change` no formulário (`_markGnModifiedIfNeeded`) que vira "Modificado" assim que o usuário mexe em algo estando limpo. Clicar no badge nesse estado explica a situação e orienta: publicar pra sincronizar, ou "Arquivo > Descartar Alterações" pra voltar ao último estado sincronizado.

### Bug 11 — Mapeamento Campo a Campo `xml_generator.py` × `xml_parser.py` (mesmo dia)

Testando o pull/import mais a fundo, o usuário notou vários campos vazios após popular o form a partir de um XML: tipo de data, data/hora do recurso, frequência de atualização (e possivelmente data da próxima atualização), código EPSG/SRC, campos de licença e idioma do metadado. Contatos vinham com os dados certos, mas sempre marcados "manual" na UI, mesmo quando vinculados ao diretório do GN.

**Investigação**: em vez de adivinhar campo por campo, comparei sistematicamente cada `d.get(...)` de `core/xml_generator.py` contra o que `core/xml_parser.py` (já expandido no Bug 8) efetivamente extraía. Achados, em ordem de descoberta:

1. **Idioma do metadado vs. idioma do dado confundidos**: `gmd:language` na raiz do `MD_Metadata` é o idioma do *metadado* (`metadataLanguage`), mas o parser jogava esse valor na chave `LanguageCode` — que na verdade é o idioma do *dado*, escrito como um `gmd:language` **separado** dentro de `id_info` (`MD_DataIdentification`). O parser nunca lia esse segundo elemento.
2. **Chave errada pra data de citação**: extraída pra `date_creation`, mas o campo real do form (`collectFormData()`) é `date`. `dateType` (CI_DateTypeCode) nunca era extraído.
3. **Blocos inteiros nunca lidos**: `referenceSystemInfo` (EPSG/SRC), `resourceMaintenance` (frequência/próxima atualização), `resourceConstraints` (licença) e `editionDate` — zero extração pra nenhum desses.
4. **Bônus, achado ao adicionar extensão temporal**: o dict de namespaces do parser tinha `gml: 'http://www.opengis.net/gml'` — mas `xml_generator.py` usa `http://www.opengis.net/gml/3.2` (com versão). Qualquer XPath futuro com prefixo `gml:` nunca teria batido com nada até essa correção.
5. **Contatos sempre "manual"**: `_parse_responsible_party()` (do Bug 8) sempre retornava `isManual: True`, independente de o `CI_ResponsibleParty` ter um atributo `uuid` real (indicando vínculo com o diretório/registry do GN). O JS usa `isManual === 'gn'` pra decidir se mostra a badge "Catálogo Online" — sem essa distinção, todo contato parecia manual mesmo quando não era.

**Fix**: `core/xml_parser.py` ganhou extração de `date`/`dateType`, `date_edition`, `metadataLanguage` (raiz, corrigido) separado de `LanguageCode` (id_info, novo), `epsgCode`/`epsgTitle`, `maintenanceFrequency`/`dateOfNextUpdate`, `useLimitation`/`accessConstraints`/`useConstraints`/`otherConstraints`, e `temporalFrom`/`temporalTo` (depois de corrigir o namespace do `gml`). `_parse_responsible_party()` agora retorna `isManual: 'gn'` quando o nó tem `uuid`, senão `True`. Validado com round-trip completo (`generate_xml` → `parse_xml_to_dict`) cobrindo os 16 campos novos de uma vez — bateu 100%.


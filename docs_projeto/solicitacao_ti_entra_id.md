# Solicitação de Infraestrutura — Autenticação Entra ID para Plugin QGIS
## Plugin GeoMetadata v2.0

**Data:** 22/04/2026  
**Solicitante:** Equipe de Geoprocessamento  
**Prioridade:** Alta — Bloqueia evolução do plugin GeoMetadata para v2.0

---

## 1. Contexto

O plugin QGIS **GeoMetadata** atualmente autentica no GeoOrchestra via **Basic Auth**.
Queremos migrar para **Entra ID (SSO corporativo)**, alinhando com a autenticação que o GeoOrchestra **já utiliza**.

### Arquitetura atual

```
Plugin QGIS ──(Basic Auth)──► GeoOrchestra Gateway ──► GeoServer / GeoNetwork
```

### Arquitetura desejada

```
Plugin QGIS ──(Bearer JWT)──► GeoOrchestra Gateway ──► GeoServer / GeoNetwork
      │                              ▲
      │  1. Login via navegador       │
      ▼                               │
  Microsoft Entra ID ─────────────────┘
  (mesmo tenant já configurado)    Valida o JWT
```

O plugin é uma **aplicação desktop** instalada no PC de cada usuário. Ele usa a biblioteca `msal-python` para abrir o navegador padrão do sistema, o usuário faz login com a conta corporativa (mesma do Teams/e-mail), e o plugin recebe um **Access Token JWT** temporário. Esse token é enviado via header `Authorization: Bearer <token>` nas chamadas REST ao Gateway.

---

## 2. O Que Precisamos

Como o GeoOrchestra **já está integrado ao Entra ID**, precisamos de apenas **um item** do time de TI:

### 2.1 App Registration (Public Client) para o Plugin

Criar um **novo registro de aplicativo** no Microsoft Entra Admin Center:

| Campo | Valor |
|-------|-------|
| **Nome** | `GeoMetadata QGIS Plugin` (ou nome a critério do TI) |
| **Supported account types** | `Accounts in this organizational directory only` (Single tenant) |
| **Redirect URI — Plataforma** | `Public client/native (mobile & desktop)` |
| **Redirect URI — Valor** | `http://localhost` |

> **Por que "Public Client"?**  
> O plugin roda no desktop do usuário (não tem servidor backend próprio).  
> A autenticação usa o fluxo **OAuth2 + PKCE** — seguro sem necessidade de Client Secret.  
> É o mesmo mecanismo que VS Code, GitHub Desktop e outras apps desktop usam.

#### API Permissions (Delegated)

Em **API Permissions → Add a Permission → Microsoft Graph → Delegated Permissions**:

| Permissão | Motivo |
|-----------|--------|
| `openid` | Login OIDC padrão |
| `profile` | Nome do usuário (exibição no plugin) |
| `email` | E-mail do usuário (usado nos metadados MGB 2.0) |

Após adicionar, clicar em **"Grant admin consent for [Organização]"**.

> **Nota:** NÃO é necessário `GroupMember.Read.All` nem configuração de grupos neste momento — o controle de permissões (quem pode publicar, quem pode editar) já é gerenciado pelo GeoOrchestra/GeoServer existente.

---

## 3. Ponto Crítico — Validação com o TI

Precisamos confirmar **uma questão técnica** com o time que administra o GeoOrchestra:

> **O Gateway GeoOrchestra aceita autenticação via header `Authorization: Bearer <JWT>` em chamadas REST?**
>
> Ou seja: se o plugin QGIS obtiver um Access Token diretamente do Entra ID (mesmo tenant) e enviar como Bearer nas chamadas à REST API do GeoServer/GeoNetwork, o Gateway aceita e autentica corretamente?

### Por que essa pergunta é importante:

- Quando um **navegador** acessa o GeoOrchestra, o Gateway faz o redirect OAuth2 e gerencia cookies de sessão — isso já funciona.
- Quando uma **aplicação desktop** (nosso plugin) acessa via REST API, ela não pode fazer redirect no browser a cada request. Ela precisa enviar o token diretamente no header HTTP.
- Se o Gateway **não** aceita Bearer JWT externo, precisaremos de uma abordagem alternativa (ex: o plugin simular o fluxo web e capturar o cookie de sessão do Gateway).

### Cenários possíveis:

| Cenário | Impacto no Plugin | Ação necessária do TI |
|---------|-------------------|----------------------|
| **Gateway aceita Bearer JWT** | ✅ Ideal — plugin envia token direto | Nenhuma config adicional no Gateway |
| **Gateway só aceita cookies de sessão** | ⚠️ Funciona — plugin faz login via browser e captura cookie | Nenhuma, mas é menos elegante |
| **Gateway precisa de ajuste para aceitar Bearer** | 🔧 Possível — Spring Security suporta Resource Server | Habilitar `oauth2-resource-server` no Gateway |

---

## 4. Informações que Precisamos de Volta

| Informação | Exemplo | Para quê |
|------------|---------|----------|
| **Application (Client) ID** | `a1b2c3d4-e5f6-...` | Configurar a lib `msal` no plugin |
| **Directory (Tenant) ID** | `f6e5d4c3-b2a1-...` | Construir a Authority URL |
| **Resposta sobre Bearer JWT** | Sim / Não / Precisa ajuste | Definir a estratégia de autenticação no plugin |

---

## 5. Ambientes

| Ambiente | URL Base | Prioridade |
|----------|----------|------------|
| **Desenvolvimento** | `https://geo-d.cdhu.sp.gov.br` | Configurar e testar primeiro |
| **Produção** | `https://geo.cdhu.sp.gov.br` | Após validação em DEV |

---

## 6. Fluxo Técnico — Como Funciona no Desktop

```
  PC DO USUÁRIO
  ┌───────────────────────────────────────────────────┐
  │                                                   │
  │  Plugin QGIS                                      │
  │  ┌────────────┐   1. Clica "Login"                │
  │  │GeoMetadata │─────────────────────────────┐     │
  │  │            │                             │     │
  │  │  (msal)    │◄──── 4. Recebe token ──┐    │     │
  │  └─────┬──────┘                        │    │     │
  │        │                         localhost  │     │
  │        │                          (temp)    │     │
  └────────│────────────────────────────│───│───┘     │
           │                            │   │         │
           │   2. Abre navegador ──────►│   │         │
           │      do sistema            │   │         │
           │                    ┌───────┘   │
           │                    │  3. Login  │
           │                    ▼  com conta │
           │              ┌──────────────┐  │
           │              │ Entra ID     │──┘
           │              │ (Azure)      │ redirect para
           │              │              │ localhost
           │              │ usuario@cdhu │
           │              │ ************ │
           │              └──────────────┘
           │
           │  5. Authorization: Bearer eyJ0eX...
           ▼
    ┌──────────────────────┐
    │  GeoOrchestra        │ ─── já valida via Entra ID
    │  geo-d.cdhu.sp.gov.br│
    │  ├── /geoserver/rest │
    │  └── /geonetwork/api │
    └──────────────────────┘
```

- O plugin **nunca vê a senha** do usuário
- O token expira em ~1h e é renovado automaticamente pela `msal`
- É o mesmo Entra ID que o GeoOrchestra já usa

---

**Contato para dúvidas:** Equipe de Geoprocessamento

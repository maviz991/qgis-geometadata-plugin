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
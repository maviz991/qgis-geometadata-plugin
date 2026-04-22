# Requisitos de Desenvolvimento — GeoMetadata v2.0

**Versão Atual em Produção:** `1.0.1`  
**Versão Alvo:** `2.0.0`  
**Ambiente de Desenvolvimento:** `https://geo-d.cdhu.sp.gov.br`  
**Ambiente de Produção:** `https://geo.cdhu.sp.gov.br`

---

## 1. Visão Geral

O objetivo da v2.0 é evoluir o plugin GeoMetadata de uma ferramenta de catalogação para um **cliente integrado de publicação geoespacial** dentro do ecossistema corporativo GeoOrchestra/CDHU.

A v1.0.1 já entrega o fluxo completo de metadados (formulário → XML MGB 2.0 → publicação no GeoNetwork com autenticação Basic Auth). A v2.0 adiciona três novas capacidades sobre essa base estável:

1. **Autenticação via Microsoft Entra ID (SSO)** como prioridade (Fase 1)
2. **Publicação de camadas vetoriais no GeoServer** (upload ou registro lógico PostgreSQL)
3. **Exportação e vínculo de estilos SLD** gerados a partir da simbologia do QGIS
4. **Edição e re-publicação de XMLs de metadados existentes**

> **Nota sobre Autenticação:** A v2.0 **prioriza** a migração para Entra ID utilizando a biblioteca `msal-python` e o fluxo PKCE. O GeoOrchestra/Gateway local já possui integração com Entra ID, o que simplifica o processo, exigindo apenas um App Registration (Public Client) e validação do header Bearer JWT.

---

## 2. Estado Atual da Base de Código (v1.0.1)

### O que está implementado e funciona

| Módulo | Descrição |
|---|---|
| `GeoMetadataDialog` | Formulário completo MGB 2.0 com tema claro/escuro adaptativo |
| `UnifiedLoginDialog` | Login Basic Auth com suporte a perfis salvos `QgsAuthConfigSelect` |
| `xml_generator.py` | Geração de XML a partir de template (`tamplate_mgb20.xml`) |
| `xml_parser.py` | Leitura e parsing de XMLs MGB 2.0 existentes |
| `layer_selection_dialog.py` | Associação de camadas WMS/WFS ao metadado |
| `plugin_config.py` | Configuração centralizada via `config.json` (URLs GeoNetwork/GeoServer) |
| Persistência dual | Sidecar file (shapefiles) + tabela PostgreSQL (camadas PostGIS) |
| Preenchimento automático | Título e BBox da camada ativa |
| Proteção de dados | Flag `form_is_dirty` + aviso ao fechar sem salvar |

### O que foi removido (limpeza v2.0)

- `auth_webview.py` — Protótipo experimental, nunca integrado à produção.
- `geoserver_login_dialog.py` — Diálogo legado substituído pelo `UnifiedLoginDialog`.

---

## 3. Requisitos Funcionais (RF) — v2.0

### Módulo A: Publicação de Dados Vetoriais no GeoServer

**RF01 — Listagem de Workspaces e DataStores**
O plugin deve acionar a REST API do GeoServer (usando a sessão autenticada existente) para listar os workspaces e datastores disponíveis. O usuário selecionará o destino em ComboBoxes antes de publicar.

**RF02 — Publicação Lógica (PostGIS)**
Para camadas cujos dados já existem no banco corporativo, o plugin envia apenas o comando de registro `FeatureType` via REST, sem tráfego de dados espaciais.
- *Pré-requisito:* A camada selecionada no QGIS deve ser do tipo PostgreSQL.

**RF03 — Upload de Arquivo (Criação e Sobrescrita)**
Para camadas locais (shapefiles, GeoPackages), o plugin converte para o formato aceito pelo GeoServer e envia via REST API.
- Suporte inicial: Shapefile (`.zip` com todos os arquivos do ESRI)
- Modos: `Criar novo` ou `Sobrescrever existente`

**RF04 — Validação de Nome de Camada (Regex)**
Antes de qualquer publicação, o plugin valida o nome da camada com regex para:
- Remover espaços e caracteres especiais (apenas `[a-z0-9_]`)
- Garantir que o nome **não começa com número** (bug conhecido do GeoServer)
- Exibir o nome sanitizado ao usuário para confirmação antes de publicar

---

### Módulo B: Exportação de Estilos (SLD)

**RF05 — Conversão de Simbologia para SLD**
Usar a API nativa do QGIS (`QgsMapLayer.exportSldStyle()`) para exportar a simbologia configurada no QGIS para o padrão OGC SLD 1.1.0.

> **Limitação documentada:** A conversão é do tipo *best-effort*. Estilos complexos (regras data-driven, blending modes, efeitos de camada) podem não ter equivalente SLD. O plugin **exibirá um aviso** ao usuário antes de exportar.

**RF06 — Envio e Vínculo do Estilo ao GeoServer**
Enviar o arquivo `.sld` gerado via REST API (`PUT /geoserver/rest/styles/{name}`) e definir como estilo padrão (`Default`) da camada publicada.

---

### Módulo C: Edição de Metadados Existentes

**RF07 — Abertura de XML Existente**
Permitir que o usuário carregue um arquivo `.xml` MGB 2.0 existente diretamente no plugin (via `QFileDialog`) para edição.
- O `xml_parser.py` já tem a base desta lógica; será exposta via botão na UI.

**RF08 — Re-publicação com UUID Preservado**
Ao exportar par o Geohab um XML carregado externamente, o plugin deve usar o UUID original do arquivo (não gerar um novo) para que a operação funcione como **atualização** (HTTP PUT) e não como criação de registro duplicado.

---

## 4. Requisitos Não Funcionais (RNF)

| ID | Requisito |
|---|---|
| RNF01 | **Compatibilidade:** Python 3, QGIS LTR 3.22+. Bibliotecas: `requests`, `lxml`, `psycopg2` (já presentes no QGIS). |
| RNF02 | **Assincronismo:** Operações de upload e conversão (RF03, RF05) devem rodar em `QThread` para não bloquear a UI do QGIS. Implementar barra de progresso `QProgressDialog`. |
| RNF03 | **Verificação de Dependências:** O script de instalação deve verificar apenas dependências reais da v2.0. `boto3` não é necessário enquanto o MinIO está em backlog. |
| RNF04 | **Sem `verify=False`:** o `session.verify = False` atual em `UnifiedLoginDialog` deve ser ajustado para aceitar o certificado corporativo via parâmetro, não desabilitando a verificação globalmente. |

---

## 5. Regras de Negócio (RN)

| ID | Regra |
|---|---|
| RN01 | **Nomenclatura de Camadas:** Regex obrigatório: `[a-z][a-z0-9_]*`. Nomes não podem começar com número. |
| RN02 | **Erro 403:** Exibir mensagem clara de "Acesso Negado — você não possui permissão de escrita neste Workspace" sem expor detalhes técnicos ao usuário. |
| RN03 | **Validação de Append:** (Backlog) Em operações de Append futuras, comparar schemas via `DescribeFeatureType` antes de enviar dados. |
| RN04 | **Aviso de SLD:** Exibir aviso informativo antes de exportar estilo, indicando que simbologia complexa pode não ser traduzida perfeitamente. |

---

## 6. Itens em Backlog (Fora do Escopo v2.0)

| Item | Razão |
|---|---|
| Upload Raster via MinIO | Depende de Service Account e definição de infraestrutura pelo time de TI |
| Modo Append (GeoServer) | Alta complexidade de validação de schema; adiado para v2.1 |

---

## 7. Plano de Implementação por Fases

### Fase 1 — Autenticação e Fundação GeoServer (Prioridade Alta)
1. **Implementar Módulo Entra ID:** Criar provedor de auth usando `msal-python` e fluxo PKCE.
2. **Abstração de Sessão:** Garantir que o plugin suporte tanto Bearer Token quanto Basic Auth (fallback).
3. Criar `geoserver_publisher.py` — classe com métodos para REST API do GeoServer
4. Implementar RF01 (listagem de workspaces/datastores)
5. Implementar RF04 (validação e sanitização de nomes)
6. Criar a aba ou wizard de publicação na UI principal

### Fase 2 — Upload e Publicação (Prioridade Alta)
7. Implementar RF02 (publicação lógica PostGIS)
8. Implementar RF03 (upload shapefile em ZIP)
9. Implementar RNF02 (QThread + barra de progresso)

### Fase 3 — Estilos SLD (Prioridade Média)
10. Implementar RF05 (exportação SLD via API QGIS)
11. Implementar RF06 (envio e vínculo ao GeoServer)

### Fase 4 — Metadados (Prioridade Média)
12. Implementar RF07 (abertura de XML existente via FileDialog)
13. Implementar RF08 (re-publicação com UUID preservado)

### Fase 5 — Qualidade e Housekeeping
14. Corrigir RNF04 (`verify=False` → certificado corporativo)
15. Refinar mensagens de erro (RN02)
16. Atualizar `metadata.txt` para versão `2.0.0`
17. Atualizar `Guide_user.html` / `Guide_user.md`

---

## 8. Verificação e Testes

### Testes de Integração (Ambiente DEV — `geo-d.cdhu.sp.gov.br`)
- Login com credenciais válidas → sessão retornada corretamente
- Listagem de workspaces → retorna lista real do GeoServer DEV
- Upload de shapefile simples → camada visível no GeoServer DEV
- Publicação lógica de tabela PostGIS → FeatureType criado
- Exportação SLD de camada categorizada simples → estilo vinculado
- Abertura de XML externo → formulário preenchido com UUID original
- Re-publicação de XML externo → UUID preservado, registro atualizado no GeoNetwork

### Verificação de UX
- Operação de upload longa não trava a janela do QGIS (QThread)
- Mensagem de erro 403 legível pelo usuário final
- Aviso SLD exibido antes da exportação

---

**Fim do Documento.** Versão: 17/04/2026

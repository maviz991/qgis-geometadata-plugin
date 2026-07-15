# Catálogo de Códigos de Erro (GeoMetadata)

Este documento descreve todos os códigos de erro padronizados retornados pelo plugin, que facilitam a identificação rápida da causa de um problema pelo suporte de TI (CDA) e pelos usuários.

## `[GS-XXX]` - GeoServer API (Erros de Comunicação e Servidor)
São mensagens geradas durante a tentativa de publicar uma camada ou aplicar um estilo no servidor de mapas.

- **`[GS-401]`**: Falha de Autenticação — o plugin não conseguiu autenticar ou não tem acesso para realizar esta operação no GeoServer (Erro 401 Unauthorized). Confirme as permissões do seu login.
- **`[GS-403]`**: Acesso Negado — você não possui permissão de escrita neste Workspace.
- **`[GS-404]`**: Workspace ou Datastore não encontrado no GeoServer.
- **`[GS-409]`**: Conflito de Nomes — Já existe um estilo ou camada com esse nome publicado no Workspace ou Datastore especificado.
- **`[GS-422]`**: Entidade Não Processável — Ocorreu quando: (1) O GeoServer não conseguiu interpretar o SLD (estilo com formato inválido para a versão do servidor) ou (2) A tabela selecionada no QGIS não possui colunas/schema correspondente no datastore remoto ou falta chave primária na tabela.
- **`[GS-500]` / `[GS-000]`**: Erro inesperado do GeoServer. Representa uma falha crua que não possuía tradução específica pré-mapeada.

---

## `[GN-XXX]` - GeoNetwork API (Catálogo de Metadados)
São mensagens geradas durante a tentativa de busca ou publicação de um metadado no catálogo oficial.

- **`[GN-401]`**: Falha na autenticação ou credenciais inválidas ao se comunicar com a API do GeoNetwork.
- **`[GN-403]`**: Privilégios insuficientes — o usuário logado não tem permissão de "revisor" ou editor no catálogo para concluir a ação.
- **`[GN-409]`**: Registro Duplicado — Já existe um metadado com este UUID no catálogo (o usuário precisa escolher a opção de sobrescrever no modal).
- **`[GN-422]`**: Falha na validação do servidor — O XML de metadado enviado possui estrutura incompatível ou valores não aceitos pelo perfil MGB 2.0.
- **`[GN-500]`**: Erro interno do servidor (NullPointerException, etc.).
- **`[GN-000]`**: Resposta inesperada do servidor GeoNetwork (fallback genérico para mensagens não reconhecidas).

---

## `[UI-XXX]` - Avisos de Interface e Validações
São bloqueios ou avisos originados diretamente na interface (frontend/QGIS) para impedir ações incorretas do usuário.

- **`[UI-001]`**: Credenciais de usuário e senha do GeoServer são obrigatórias na aba de configurações.
- **`[UI-002]`**: Destino de publicação incompleto (Faltou selecionar um workspace ou preencher um nome para publicar a camada).
- **`[UI-003]`**: É necessário escolher um estilo na aba de "Estilos" antes de tentar forçar a atualização do estilo no servidor.
- **`[UI-004]`**: Camada não publicável (Faltam os requisitos mínimos detectados pelo plugin, como não ter uma tabela de dados associada).
- **`[UI-005]` / `[UI-006]`**: Bloqueio de validação (Ex: bordas vermelhas no formulário) exigindo o preenchimento de campos obrigatórios no painel "Editar Metadados" antes de permitir a exportação em disco ou a publicação no portal.
- **`[UI-007]`**: Usuário precisa estar logado no sistema unificado do Geohab para publicar o metadado na rede.
- **`[UI-008]`**: É necessário selecionar uma camada ativa na "Árvore de Camadas" do QGIS antes de interagir com as ações de leitura/escrita.
- **`[UI-009]`**: O plugin não conseguiu identificar a qual tabela do banco de dados a camada ativa pertence (útil para camadas de WMS/WFS soltas ou dados temporários corrompidos).
- **`[UI-010]`**: Aviso indicando que a camada selecionada não existe como um arquivo de vetor físico no disco, sendo impossível gravar um "XML sidecar" na mesma pasta.

---

## `[SYS-XXX]` - Exceções e Erros de Sistema do Plugin
São erros gerados pela própria infraestrutura interna do plugin durante execuções locais.

- **`[SYS-001]`**: Serviço de comunicação do GeoServer não foi inicializado internamente (Geralmente indica inicialização prematura ou bypass do fluxo de login).
- **`[SYS-002]`**: Falha técnica ao ler ou analisar o arquivo estático de contatos institucionais embutido no QGIS (`assets/contacts.json`).
- **`[SYS-003]` / `[SYS-004]`**: Falha ao empacotar os dados ou transformar a matriz de metadados visuais em um texto de sintaxe XML válida usando a biblioteca `lxml`.
- **`[SYS-005]`**: A biblioteca `psycopg2` não foi encontrada no ambiente Python do QGIS (impossível se conectar a tabelas do PostgreSQL).

---

## `[DB-XXX]` - Persistência e Banco de Dados (Erros Locais)
São falhas ocorridas ao tentar gravar dados (seja no banco PostgreSQL ou no disco do computador).

- **`[DB-001]`**: Não foi possível descriptografar/carregar as configurações do Authentication Manager do QGIS (config id inválido ou master password ausente).
- **`[DB-002]`**: Falha ao inserir o registro na tabela de metadados local do PostgreSQL (ex: tabela `qgis_geometadata_plugin` não provisionada no schema `public` pelo administrador).
- **`[DB-003]`**: Falha de permissão no Sistema Operacional (ex: pasta de apenas leitura) impedindo a gravação do arquivo `.xml` junto ao Shapefile ou GeoPackage original.

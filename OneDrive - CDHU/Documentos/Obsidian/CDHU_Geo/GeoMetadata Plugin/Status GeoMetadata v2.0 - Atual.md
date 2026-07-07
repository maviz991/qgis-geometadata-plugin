# Status Report: GeoMetadata Plugin (06/Maio/2026)

## Nova Arquitetura Modular

O plugin foi totalmente refatorado para seguir padrões profissionais de desenvolvimento:

- **`core/`**: Toda a lógica de negócio (XML, persistência, autenticação, serviços).
- **`ui/`**: Interface desacoplada da lógica, usando formulários dinâmicos e pontes web.
- **`assets/`**: Centralização de configurações (`config.json`), ícones e estilos.

## Autenticação e Segurança (Entra ID)

- **Implementado:** Integração com **Microsoft Entra ID (Azure AD)** via biblioteca `msal`.
- **SSO (Single Sign-On):** O plugin agora suporta login institucional, eliminando a necessidade de gerenciar senhas locais.
- **Unified Login:** Diálogo unificado que suporta tanto o login via Entra ID quanto o login tradicional do GeoNetwork.

## Persistência e Sessão

- **Login Persistente:** A sessão (`api_session`) agora é armazenada na instância principal do plugin (`GeoMetadata.py`), garantindo que o usuário permaneça logado durante toda a sessão do QGIS.
- **Persistence Service:** Novo serviço centralizado para gerenciar estados e configurações locais de forma segura.

## Interface e UX (Refinada)

- **Estilização Externa:** O design agora é controlado via **`ui/styles.css`**, permitindo atualizações visuais rápidas sem mexer no código Python.
- **Formulários Dinâmicos:** Uso de `dynamic_form.py` para gerar campos de metadados com base no esquema necessário.
- **Dependências Automáticas:** O plugin agora detecta e instala bibliotecas faltantes (como o `msal` e `PyQtWebEngine`) automaticamente no primeiro uso via `env_checker.py`.

## Integração com GeoServer e GeoNetwork

- **GeoServer Panel:** Nova interface para gerenciar a publicação de camadas diretamente do QGIS.
- **XML ISO 19115/19139:** Geração de metadados robusta e validada contra o esquema oficial do GeoNetwork.

---

# Diário de Bordo — 08/Maio/2026

## Formulário de Contatos — Refatoração e Novos Recursos

### Validação de Campos

- **CEP:** limitado a 8 dígitos em tempo real; hífen adicionado apenas ao perder foco.
- **Telefone:** máximo 13 dígitos para Brasil (DDI 55); se o usuário digitar `+`, aceita qualquer formato internacional (máx. 15 dígitos).
- **Sigla:** não aceita espaços (conversão para maiúsculas em tempo real).
- **Campos obrigatórios no formulário manual:** todos os campos exceto Cargo são obrigatórios, incluindo Regra (select), Logradouro, Número, Complemento, Bairro, Cidade, Estado, CEP e País.
- **Limpeza de erro em tempo real:** ao digitar em qualquer campo com borda vermelha, o erro some imediatamente. Para selects, o erro some ao mudar a opção (`change` listener).

### Accordion de Contatos

- **Badges restaurados** nos cabeçalhos do accordion e nas sugestões de pesquisa: _Catálogo Online_ (GN), _Catálogo Offline_ (preset), _Manual_, _Meus Contatos_.
- **Edição in-place:** contatos manuais e "Meus Contatos" ganham botões Editar / Salvar / Cancelar. Contatos do catálogo permanecem somente leitura.
- **Exportar XML:** botão disponível em todos os contatos para exportar ISO 19139 `gmd:CI_ResponsibleParty`.
- **Salvar localmente:** contatos manuais podem ser salvos em `geometadata_user_contacts.json` (perfil QGIS) e reaparecem nas sugestões em futuras sessões com badge _Meus Contatos_.
- **Exclusão com confirmação:** botão Excluir em contatos salvos localmente, com diálogo de confirmação antes de remover do arquivo.
- **Deduplicação:** ao adicionar contato da lista de sugestões, o sistema verifica duplicidade por `_key` ou combinação sigla+org+email.

### Endereço

- **Segmentação:** Logradouro, Nº, Complemento e Bairro ficam na mesma linha (`address-split` com 4 inputs flex).
- **Exibição readonly:** todos os 4 campos são concatenados em uma única linha no accordion fechado via `_combineAddr`.
- **Mensagens de erro** nos campos de endereço aparecem abaixo de cada input (cada input envolto em `.addr-field-wrap` flex-column, corrigindo o bug onde a mensagem aparecia à direita do campo).

### Ícones de Ajuda (?)

- Adicionados botões `?` com tooltip em todos os campos dos 3 formulários manuais (Contato, Processador, Metadado): Sigla, Organização, E-mail, Regra, Cargo, Telefone, Endereço, Cidade, Estado, CEP e País.

### Data e Hora do Metadado

- Campo **Data e hora de criação do metadado** agora é pré-preenchido com UTC-3 (horário de Brasília). Não é sobrescrito se o usuário já tiver preenchido o campo.

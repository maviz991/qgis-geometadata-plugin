## **Manual do Usuário – Plugin GeoMetadata para QGIS**

**Versão:** 1.0.1  
**Data:** 27 Nov de 2025

### **1. Introdução**

Bem-vindo ao **GeoMetadata | Geohab Plugin**, o plugin oficial da CDHU para a criação e gerenciamento de metadados geoespaciais.

Esta ferramenta foi desenvolvida para simplificar, padronizar e centralizar a documentação de nossas camadas, seguindo o padrão ISO 19115 e garantindo a integração perfeita com o nosso catálogo de dados do **Geohab**.

Com este plugin, você pode:
*   Criar metadados ricos e padronizados diretamente no QGIS.
*   Carregar e editar metadados já existentes.
*   Associar suas camadas a serviços web (WMS/WFS) do nosso GeoServer.
*   Exportar metadados para o Geohab com segurança e consistência.

### **2. Instalação**

O plugin GeoMetadata é distribuído internamente. Para instalá-lo:
1.  Receba o arquivo `.zip` do plugin.
2.  No QGIS, vá até o menu **Complementos > Gerenciar e Instalar Complementos...**.
3.  Na janela que se abre, selecione a aba **Instalar a partir de ZIP**.
4.  Clique no botão `...` e selecione o arquivo `.zip` que você recebeu.
5.  Clique em **Instalar Complemento**.
6.  Após a instalação, um novo ícone da CDHU aparecerá na sua barra de ferramentas.

### **3. Visão Geral da Interface**

Ao clicar no ícone do plugin, a janela principal será aberta. Ela é dividida em três áreas principais:



#### **A. Cabeçalho (Barra de Ações)**
É aqui que ficam as ações principais:
*   **Exportar Metadado:** Salva o metadado como um arquivo `.xml` no seu computador. Útil para backups ou compartilhamento.
*   **Continuar depois:** Salva o seu progresso atual junto à camada. Permite que você feche o plugin e, ao reabri-lo na mesma camada, todos os dados estarão lá.
*   **Exportar para Geohab:** A ação final. Envia o metadado para o catálogo oficial da CDHU.
*   **Associar Camada:** Abre uma janela para vincular sua camada a um serviço WMS ou WFS existente no GeoServer.
*   **Entrar / [Seu Nome]:** Botão para fazer login no Geohab. Uma vez logado, ele exibe seu nome e permite desconectar.

#### **B. Formulário Principal**
É onde você preenche as informações do metadado. Os campos são agrupados logicamente:
*   **Identificação:** Título, Data de Criação, Resumo, Status, Palavras-chave.
*   **Contato:** Informações sobre o responsável pelos dados. Use os **Setores CDHU** para preencher automaticamente os dados de contato dos setores mais comuns.
*   **Detalhes Técnicos:** Tipo, Escala, Idioma, etc.
*   **Extensão Geográfica (Bounding Box):** Os campos Norte, Sul, Leste e Oeste são **preenchidos automaticamente** a partir da camada selecionada no QGIS e não podem ser editados. Isso garante que a extensão no metadado sempre reflita a realidade da camada.
*   **URL Thumbnail:** Um link para uma imagem de pré-visualização da camada.

#### **C. Painel de Camadas Associadas**
Mostra quais serviços (WMS/WFS) do GeoServer foram vinculados a este metadado. Você pode remover uma associação clicando no ícone `X`.

---

### **4. Passo a Passo: Principais Tarefas**

#### **Tarefa 1: Criar um Novo Metadado**

1.  **Carregue a Camada:** Abra o QGIS e adicione a camada para a qual você deseja criar o metadado (Local ou do banco de dados PostgreSQL). Certifique-se de que ela esteja **selecionada** no Painel de Camadas.
2.  **Abra o Plugin:** Clique no ícone do GeoMetadata.
3.  **Verifique os Campos Automáticos:** Note que o **Título** (baseado no nome da camada) e a **Extensão Geográfica** (Bounding Box) já foram preenchidos para você.
4.  **Faça Login:** Clique em **ENTRAR** no canto superior direito. Use uma configuração salva do QGIS ou digite seu usuário e senha da rede. O login é necessário para associar camadas e exportar para o Geohab.
5.  **Preencha os Campos:** Complete os campos obrigatórios, como **Resumo** e **Palavras-chave**.
    *   **Dica:** Para as palavras-chave, separe-as por **vírgula (`,`)**. O sistema também entende ponto-e-vírgula (`;`) e corrige automaticamente.
    *   **Dica:** Para a **Escala**, digite apenas o número (ex: `5000`). O sistema é inteligente e consegue extrair o número de formatos como `1:5.000`.
6.  **Defina o Contato:** Use o menu **Setores CDHU** para escolher um preset (ex: "DPDU") e preencher os dados de contato automaticamente.
7.  **(Opcional) Associe uma Camada:**
    *   Clique em **Associar Camada**.
    *   Selecione o tipo de serviço (WMS ou WFS).
    *   Comece a digitar o nome da camada no campo de busca para filtrar a lista.
    *   Clique na camada desejada e depois em **Adicionar Serviço**.
    *   Clique em **OK**.
8.  **Salve ou Exporte:**
    *   Se quiser salvar e continuar depois, clique em **Continuar depois**.
    *   Se o metadado estiver completo e pronto, clique em **Exportar para Geohab**.

#### **Tarefa 2: Editar um Metadado Existente**

1.  **Selecione a Camada:** No QGIS, selecione a camada cujo metadado você já salvou anteriormente (seja localmente ou no banco de dados).
2.  **Abra o Plugin:** Clique no ícone do GeoMetadata.
3.  **Carregamento:** O plugin detectará o metadado salvo e preencherá todos os campos do formulário automaticamente.
4.  **Edite e Salve:** Faça as alterações desejadas e use os botões **Continuar depois** ou **Exportar para Geohab** para salvar suas modificações.
    *   **Importante:** Note que a **Extensão Geográfica** será sempre atualizada para refletir o estado *atual* da camada, mesmo que você tenha carregado um metadado antigo. Isso garante que a informação esteja sempre correta.

### **5. Solução de Problemas (FAQ)**

*   **Aparece a mensagem "Campos Faltando" ao tentar exportar.**
    *   **Causa:** Você não preencheu todos os campos obrigatórios (como Título, Resumo, etc.).
    *   **Solução:** Preencha os campos listados na mensagem de erro e tente novamente.

*   **Não consigo fazer login no Geohab.**
    *   **Causa:** Usuário/senha incorretos, ou você não está conectado à rede da CDHU (ou VPN).
    *   **Solução:** Verifique suas credenciais e sua conexão de rede.

*   **O plugin está com um tema claro, mas meu QGIS está com tema escuro (ou vice-versa).**
    *   **Causa:** O plugin detecta o tema do QGIS na inicialização.
    *   **Solução:** O plugin se adaptará automaticamente ao tema do QGIS. Se você mudar o tema do QGIS, é necessário **reiniciar o QGIS** para que o plugin também mude de cor.

*   **Os botões de "Exportar para Geohab" e "Associar Camada" estão desabilitados.**
    *   **Causa:** Você não está logado.
    *   **Solução:** Clique no botão **ENTRAR** e faça a autenticação.

### **6. Suporte**

Em caso de dúvidas, erros ou sugestões, por favor, abra um CDA.
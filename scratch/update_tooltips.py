import re
import os

files = [
    'ui/templates/panels/editor.html',
    'editando.html'
]

# Replacement dictionary for help-btn data-tip attributes
data_tip_replacements = {
    r'Nome completo e descritivo do conjunto de dados geoespaciais\.': 'Insira um título claro e autodescritivo. Recomenda-se incluir o tema, a localização e o ano se aplicável.',
    r'Tipo e valor da data de referência do dado:.*': 'Selecione o tipo: Criação (quando gerado), Publicação (quando divulgado) ou Revisão (última atualização relevante).',
    r'Número da versão ou edição do dado \(0 = primeira versão\)\.': 'Indique a versão do dado (ex: 1, 2, 3). Comece com 0 ou 1 para a primeira versão.',
    r'Data em que esta edição específica foi publicada ou revisada\.': 'Especifique a data exata ou aproximada de conclusão desta versão.',
    r'Descrição detalhada do conteúdo, cobertura geográfica e temática do dado\.': 'Forneça um resumo detalhado: explique o que o dado representa, sua abrangência espacial, atributos principais e o contexto de sua produção.',
    r'Objetivos para os quais o dado foi criado e uso previsto\.': 'Explique a finalidade da criação do dado: qual problema visa resolver ou para qual projeto foi demandado?',
    r'Nome do técnico ou equipe responsável pela produção dos dados\.': 'Mencione a equipe, departamento ou técnico diretamente responsável pela elaboração técnica deste dado.',
    r'Situação atual do conjunto de dados\.': 'Indique o estágio de produção atual (ex: Contínuo para dados sempre em atualização, Concluído para dados finalizados).',
    r'Termos que descrevem o conteúdo do dado, facilitando a busca e descoberta\..*': 'Adicione palavras-chave (temas, locais, métodos) para facilitar a busca no catálogo. Pressione Enter para cada termo.',
    r'Abreviação ou acrônimo da organização.*': 'Informe a sigla oficial da instituição (ex: CDHU, IBGE). Use apenas letras maiúsculas.',
    r'Nome completo da organização responsável\.': 'Informe o nome institucional completo da organização, sem abreviações.',
    r'Endereço de e-mail institucional para contato\.': 'Forneça um e-mail corporativo ou do setor responsável para eventuais dúvidas sobre o dado.',
    r'Papel desta organização em relação ao dado.*': 'Selecione a responsabilidade: Dono detém direitos, Autor criou, Ponto de Contato atende a dúvidas.',
    r'Cargo ou departamento do responsável na organização.*': 'Indique o setor, gerência ou cargo responsável para direcionar contatos futuros.',
    r'Telefone com DDD.*': 'Informe o telefone de contato do setor responsável (ex: +55 11 3111-0000).',
    r'Preencha logradouro, número e complemento separadamente\.': 'Informe o endereço físico completo da organização ou setor.',
    r'Código de Endereçamento Postal com 8 dígitos.*': 'Informe o CEP (somente números).',
    r'Com que periodicidade o dado é revisado ou atualizado\.': 'Indique com que frequência o dado sofre alterações (ex: anual, mensal, ou contínuo se não houver intervalo fixo).',
    r'Previsão de quando o dado será revisado ou atualizado novamente\.': 'Se aplicável, estime a data da próxima atualização do conjunto de dados.',
    r'Formato estrutural ou geométrico do dado geoespacial\.': 'Selecione o formato dos dados: Vetor (pontos, linhas, polígonos) ou Grid/Raster (imagens, grades de elevação).',
    r'Categoria principal da ISO 19115 que melhor descreve o conteúdo do dado\.': 'Selecione a categoria temática principal padronizada que classifica este dado.',
    r'Nível da hierarquia de metadados\. \'Conjunto de dados\' é o mais comum\.': 'Define o escopo da descrição. Em geral, utiliza-se Conjunto de dados (dataset).',
    r'Idioma principal dos conteúdos e atributos do dado\.': 'Selecione o idioma em que a tabela de atributos e as descrições estão preenchidas.',
    r'Padrão de codificação dos textos e atributos\. UTF-8 é o recomendado.*': 'Codificação dos caracteres da tabela. UTF-8 é o padrão para evitar problemas com acentuação.',
    r'Endereço de uma imagem de prévia ou mapa de localização.*': 'URL para uma miniatura (thumbnail) que será exibida nos catálogos para ilustrar o dado.',
    r'Retângulo envolvente do dado em graus decimais.*': 'Limites geográficos do dado (Bounding Box). Clique em Capturar da camada para preencher com a camada atual no QGIS.',
    r'Sistema de Referência de Coordenadas \(SRC\) do dado.*': 'Selecione o Sistema de Coordenadas em que os dados estão armazenados.',
    r'Nome completo do Sistema de Referência de Coordenadas.*': 'Nome completo do Sistema de Referência, preenchido automaticamente ao escolher o EPSG.',
    r'Denominador da escala de captura ou publicação do dado.*': 'Informe apenas o número do denominador da escala original do dado (ex: 10000 para a escala 1:10.000).',
    r'Valor mínimo de altitude.*': 'Elevação mínima (cota Z) encontrada nos dados. Deixe em branco se for dado 2D.',
    r'Valor máximo de altitude.*': 'Elevação máxima (cota Z) encontrada nos dados.',
    r'Data de início do período temporal coberto pelos dados.*': 'Data inicial que o dado representa (ex: início da coleta de imagens ou período de validade do dado).',
    r'Data de fim do período temporal coberto pelos dados\.': 'Data final que o dado representa.',
    r'Histórico de produção do dado: fontes utilizadas, metodologia.*': 'Descreva detalhadamente a metodologia, histórico de produção e as ferramentas utilizadas para gerar o dado final.',
    r'Descrição técnica das etapas de processamento realizadas.*': 'Liste e descreva as etapas de geoprocessamento, análises ou conversões feitas sobre os dados originais.',
    r'Identificação e descrição das fontes primárias utilizadas.*': 'Descreva detalhadamente as fontes utilizadas (ex: dados do IBGE de 2022, imagens de satélite Sentinel-2).',
    r'Padrão de acesso ao recurso online\.': 'Selecione o protocolo do serviço. OGC:WMS para visualização, OGC:WFS para download/vetor, ou WWW:LINK para site.',
    r'Licença que rege o uso, reprodução e redistribuição do dado\.': 'Selecione os termos de licença e direitos de uso aplicáveis a quem for utilizar estes dados.',
    r'Restrições ou condições específicas para uso do dado.*': 'Descreva de forma explícita o que NÃO é permitido fazer com o dado, se houver limitações específicas.',
    r'Tipo de restrição que controla quem pode acessar o dado\.': 'Restrições formais sobre quem pode ter acesso de leitura a este conjunto de dados.',
    r'Tipo de restrição que controla como o dado pode ser utilizado após o acesso\.': 'Restrições formais de como os dados podem ser utilizados após o acesso ter sido concedido.',
    r'Texto de atribuição ou condições complementares de direitos autorais.*': 'Texto legal de direitos autorais ou nota de rodapé (ex: (c) Secretaria do Meio Ambiente - Todos os direitos reservados).',
    r'UUID gerado automaticamente para identificar unicamente.*': 'Identificador Único Universal (UUID). É gerado automaticamente e serve para referenciar este metadado no catálogo.',
    r'Idioma em que os campos textuais deste metadado estão escritos.*': 'O idioma no qual você está escrevendo estes metadados (normalmente Português).',
    r'Data em que este registro de metadado foi criado ou atualizado pela última vez\.': 'A data da última alteração feita neste registro de metadado.'
}

# Add role titles
role_titles = {
    '"owner"': '"owner" title="Proprietário legal ou institucional do dado"',
    '"author"': '"author" title="Autor principal ou criador técnico do dado"',
    '"processor"': '"processor" title="Responsável pelo processamento ou organização do dado"',
    '"distributor"': '"distributor" title="Responsável por distribuir ou publicar o dado"',
    '"custodian"': '"custodian" title="Guardião ou mantenedor responsável pelo armazenamento"',
    '"resourceProvider"': '"resourceProvider" title="Fornecedor da infraestrutura ou recurso"',
    '"principalInvestigator"': '"principalInvestigator" title="Pesquisador ou líder do projeto"',
    '"originator"': '"originator" title="Origem ou fonte primária da informação"',
    '"pointOfContact"': '"pointOfContact" title="Contato principal para tirar dúvidas sobre o dado"',
    '"publisher"': '"publisher" title="Entidade que realizou a publicação oficial"',
    '"user"': '"user" title="Usuário ou consumidor final do dado"'
}

for filepath in files:
    if not os.path.exists(filepath):
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Replace data-tips
    for old_pattern, new_text in data_tip_replacements.items():
        # Replace removing possible \u200b and normal spaces matching
        # the pattern inside the data-tip="..."
        content = re.sub(rf'data-tip="{old_pattern}"', f'data-tip="{new_text}"', content)
        
    # 2. Add titles to role options
    # The role options don't currently have title tags, so replacing the value attributes
    for old_val, new_val in role_titles.items():
        # Prevent double adding
        if f'{new_val}' not in content:
            content = content.replace(f'value={old_val}', f'value={new_val}')

    # 3. Add title attributes to specific inputs (tooltips without help btn)
    # Inputs that could benefit from tooltips:
    inputs_with_titles = [
        ('id="f-title" type="text" placeholder="Título do conjunto de dados..."', 'id="f-title" type="text" placeholder="Título do conjunto de dados..." title="Nome descritivo. Recomendação: Tema, local e ano."'),
        ('id="f-abstract" rows="4"', 'id="f-abstract" rows="4" title="Resumo compreensível abordando os elementos chave dos dados."'),
        ('id="f-credit" type="text"', 'id="f-credit" type="text" title="Pessoa ou setor responsável pela elaboração técnica."'),
        ('id="kw-input" type="text"', 'id="kw-input" type="text" title="Pressione Enter após digitar cada palavra-chave."'),
        ('id="mf-sigla" type="text"', 'id="mf-sigla" type="text" title="Sigla do órgão. Ex: SMA, INPE, IBGE."'),
        ('id="mf-org" type="text"', 'id="mf-org" type="text" title="Nome corporativo extenso do órgão."'),
        ('class="addr-street"', 'class="addr-street" title="Nome da rua, avenida, rodovia, etc."'),
        ('class="addr-num"', 'class="addr-num" title="Número ou S/N"'),
        ('class="addr-comp"', 'class="addr-comp" title="Complemento (sala, andar, bloco)"'),
        ('class="addr-bairro"', 'class="addr-bairro" title="Bairro ou distrito"'),
        ('id="dist-search" type="text"', 'id="dist-search" type="text" title="Pesquisa as camadas disponíveis diretamente no GeoServer configurado."')
    ]
    
    for old, new in inputs_with_titles:
        if new not in content:
            content = content.replace(old, new)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated {filepath}")

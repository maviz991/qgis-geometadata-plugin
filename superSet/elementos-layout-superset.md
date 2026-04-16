# Elementos de Layout — Superset Dashboard CSS Template

> **Como usar:** No componente **Text** do Superset, insira o HTML com a classe desejada.  
> A aparência segue a variável `--conector-cor` definida no bloco `:root` do CSS.

---

## Como inserir no dashboard

1. No dashboard, clique em **Edit dashboard**
2. Arraste um componente **Text** para o layout
3. Clique em **Edit** no componente
4. Ative o modo **Markdown** e insira o HTML:

```html
<div class="seta-baixo"></div>
```

---

## Variáveis configuráveis (bloco `:root`)

| Variável | Padrão | Descrição |
|---|---|---|
| `--painel-fundo` | `transparent` | Cor de fundo do dashboard |
| `--card-fundo` | `#ccc` | Cor de fundo dos cards |
| `--card-arredondamento` | `35px` | Arredondamento dos cantos |
| `--card-borda-espessura` | `0px` | Espessura da borda (`0px` = sem borda) |
| `--card-borda-cor` | `#cccccc` | Cor da borda dos cards |
| `--card-borda-estilo` | `solid` | Estilo: `solid`, `dashed`, `dotted` |
| `--card-sombra` | `none` | Sombra: `none` ou `0 2px 8px rgba(0,0,0,0.15)` |
| `--numero-negrito` | `500` | Negrito do número: `400`=normal, `700`=bold |
| `--subtitulo-cor` | `inherit` | Cor do subtítulo |
| `--subtitulo-tamanho` | `14px` | Tamanho da fonte do subtítulo |
| `--subtitulo-negrito` | `400` | Negrito do subtítulo |
| `--cor-azul` | `#A9C9D0` | Grupo de cards azul |
| `--cor-laranja` | `#f4e3c6` | Grupo de cards laranja |
| `--cor-vermelho` | `#ecb7b7` | Grupo de cards vermelho |
| `--cor-verde` | `#c8e6c9` | Grupo de cards verde |
| `--cor-roxo` | `#d1c4e9` | Grupo de cards roxo |
| `--conector-cor` | `#cccccc` | Cor das setas, linhas e símbolos |

> **Nota:** A cor do número nos charts Big Number é controlada pelo próprio Superset  
> (Edit chart → Customize → Font color) — não é sobrescrita pelo CSS.

---

## Grupos de cores de cards

Para pintar um card de uma cor específica, adicione o nome exato do chart no bloco correspondente:

```css
/* --- GRUPO AZUL (--cor-azul) --- */
.dashboard-component-chart-holder .chart-slice[data-test-chart-name="Nome do chart"] {
    background-color: var(--cor-azul) !important;
    border-color: var(--cor-azul) !important;
}
```

A borda acompanha automaticamente a cor do grupo quando `--card-borda-espessura` for maior que `0px`.

---

## Referência de elementos de layout

### Setas verticais

| Classe | Descrição | HTML |
|---|---|---|
| `seta-baixo` | Linha vertical sólida com seta ▼ | `<div class="seta-baixo"></div>` |
| `seta-baixo-tracejada` | Linha tracejada vertical com seta ▼ | `<div class="seta-baixo-tracejada"></div>` |
| `seta-cima` | Linha vertical sólida com seta ▲ | `<div class="seta-cima"></div>` |
| `seta-cima-tracejada` | Linha tracejada vertical com seta ▲ | `<div class="seta-cima-tracejada"></div>` |

### Setas horizontais

| Classe | Descrição | HTML |
|---|---|---|
| `seta-direita` | Linha horizontal sólida com seta ► | `<div class="seta-direita"></div>` |
| `seta-direita-tracejada` | Linha tracejada horizontal com seta ► | `<div class="seta-direita-tracejada"></div>` |
| `seta-esquerda` | Linha horizontal sólida com seta ◄ | `<div class="seta-esquerda"></div>` |
| `seta-esquerda-tracejada` | Linha tracejada horizontal com seta ◄ | `<div class="seta-esquerda-tracejada"></div>` |

### Bifurcações (forks)

| Classe | Esquema visual | Descrição | HTML |
|---|---|---|---|
| `fork-chave` | `\|   \|` → `\|` | Chave em "U" — 2 entradas → 1 saída (de cima pra baixo) | `<div class="fork-chave"></div>` |
| `fork-chave-inv` | `\|` → `\|   \|` | Chave em "∩" — 1 entrada → 2 saídas (de baixo pra cima) | `<div class="fork-chave-inv"></div>` |
| `fork-3` | `\| \| \|` → `\|` | Pente — 3 entradas (esq, centro, dir) → 1 saída | `<div class="fork-3"></div>` |

**Esquema fork-3:**
```
  |      |      |    ← 3 entradas: esquerda, centro, direita
  └──────┼──────┘
         |           ← 1 saída
```

### Linhas separadoras

| Classe | Descrição | HTML |
|---|---|---|
| `linha-h` | Linha horizontal sólida | `<div class="linha-h"></div>` |
| `linha-h-tracejada` | Linha horizontal tracejada | `<div class="linha-h-tracejada"></div>` |

### Símbolos matemáticos

| Classe | Descrição | HTML |
|---|---|---|
| `sinal-mais` | Símbolo **+** grande | `<div class="sinal-mais">+</div>` |
| `sinal-igual` | Símbolo **=** grande | `<div class="sinal-igual">=</div>` |

> **Atenção:** O caractere deve ser escrito **dentro** do `<div>`.

### Rótulos e logos

| Classe | Descrição | HTML |
|---|---|---|
| `label-categoria` | Badge/rótulo de texto centralizado | `<div class="label-categoria">Grupo A</div>` |
| `logo-cdhu` | Logo CDHU (SVG embutido) | `<div class="logo-cdhu"></div>` |
| `logo-projeto` | Logo do projeto (configure a URL no CSS) | `<div class="logo-projeto"></div>` |

---

## Exemplos combinados

### Fluxo vertical simples

```html
<div class="label-categoria">Entrada</div>
<div class="seta-baixo"></div>
<div class="label-categoria">Processo</div>
<div class="seta-baixo"></div>
<div class="label-categoria">Saída</div>
```

### Convergência de 2 para 1

```html
<!-- dois cards acima, depois o fork converge pra 1 -->
<div class="fork-chave"></div>
<div class="seta-baixo"></div>
<div class="label-categoria">Resultado</div>
```

### Convergência de 3 para 1

```html
<!-- três cards acima (esquerda, centro, direita), fork-3 converge pra 1 -->
<div class="fork-3"></div>
<div class="seta-baixo"></div>
<div class="label-categoria">Resultado</div>
```

### Soma de valores

```html
<div class="label-categoria">Valor A</div>
<div class="sinal-mais">+</div>
<div class="label-categoria">Valor B</div>
<div class="sinal-igual">=</div>
<div class="label-categoria">Total</div>
```

### Fluxo tracejado (dado estimado / projetado)

```html
<div class="label-categoria">Dado real</div>
<div class="seta-baixo-tracejada"></div>
<div class="label-categoria">Projeção</div>
```

---

## Personalização por instância

Para ajustar tamanho ou cor de um elemento específico, use estilo inline:

```html
<!-- seta mais alta -->
<div class="seta-baixo" style="height: 80px;"></div>

<!-- fork mais largo -->
<div class="fork-3" style="width: 90%;"></div>

<!-- badge com cor diferente -->
<div class="label-categoria" style="background-color: #A9C9D0; color: #333;">Destaque</div>
```

---

*Template gerado para Apache Superset — cole o CSS no campo Edit dashboard → CSS*

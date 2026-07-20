# -*- coding: utf-8 -*-
"""
build.py - Manual online do Geohab Plugin (GeoMetadata)
=========================================================
Monta as paginas estaticas finais em dist/ a partir de:
  - partials/        head/nav/footer, compartilhados por todas as paginas
  - pages/            conteudo de cada pagina do manual
  - vendor_mockups/   mockups de UI feitos com o HTML real do plugin (dado
    fake, sem screenshot) - citam o CSS real via caminho relativo, entao
    ficam identicos ao app de verdade em vez de uma imagem que envelhece.
    IMPORTANTE: os fragmentos de painel do plugin (home.html, editor.html,
    etc.) sao injetados como innerHTML dentro de main.html, entao os
    caminhos relativos que eles usam (ex.: "../../img/x.png") sao relativos
    a ui/templates/ (pasta de main.html), NAO a ui/templates/panels/. Por
    isso os mockups vivem em vendor_mockups/ui/templates/*.html (mesmo
    nivel de main.html) e nao em .../panels/ - assim da pra colar o HTML
    original sem reescrever nenhum caminho.
  - o CSS real do plugin (ui/templates/css/*.css) e a pasta img/ do
    plugin: copiados AO VIVO da fonte a cada build, nunca a mao - depois de
    um facelift no plugin, so rodar "python build.py" de novo aqui atualiza
    todos os mockups sem precisar editar nada neste repositorio de docs.

Uso:
    cd docs_site
    python build.py

Saida: dist/ (sobe direto pro bucket do MinIO, sem nenhum outro build step).
"""
import re
import shutil
from pathlib import Path

DOCS_SITE = Path(__file__).resolve().parent
PLUGIN_ROOT = DOCS_SITE.parent
DIST = DOCS_SITE / "dist"

# id do arquivo (sem .html) -> titulo da pagina, na ordem em que aparecem na navbar
PAGES = [
    ("index", "Início"),
    ("interface", "Visão Geral da Interface"),
    ("metadados", "Metadados (GeoNetwork)"),
    ("geoserver", "Publicar Camada (GeoServer)"),
    ("escala-equivalente", "Escala Equivalente"),
    ("faq", "Solução de Problemas"),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_nav(active_id: str) -> str:
    """Reaproveita partials/nav.html pra toda pagina, so marcando o link
    correspondente como .active via o atributo data-page="<id>" que cada
    <a> ja carrega."""
    nav_template = read(DOCS_SITE / "partials" / "nav.html")

    def mark_active(match):
        page_id = match.group(1)
        cls = ' class="active"' if page_id == active_id else ""
        return f'data-page="{page_id}"{cls}'

    return re.sub(r'data-page="([\w-]+)"', mark_active, nav_template)


def vendor_assets():
    """Copia (nao move/edita) o CSS e as imagens REAIS do plugin pra dentro
    de dist/, espelhando a mesma profundidade de pastas que elas tem no
    plugin (ui/templates/css/, img/). Isso e o que permite que os mockups
    usem os MESMOS caminhos relativos (../../img/..., ../../../img/...)
    que os arquivos originais do plugin usam, sem reescrever nada."""
    vendor_css_dst = DIST / "vendor" / "ui" / "templates" / "css"
    vendor_css_dst.mkdir(parents=True, exist_ok=True)
    for name in ("styles.css", "geonetwork.css", "geoserver.css"):
        shutil.copy(PLUGIN_ROOT / "ui" / "templates" / "css" / name, vendor_css_dst / name)
        print(f"  [css vendorizado] {name}")

    vendor_img_dst = DIST / "vendor" / "img"
    if vendor_img_dst.exists():
        shutil.rmtree(vendor_img_dst)
    shutil.copytree(PLUGIN_ROOT / "img", vendor_img_dst)
    print("  [img vendorizada] img/*")

    # logo.png fica na raiz do plugin (nao dentro de img/) - login.html referencia
    # "../../logo.png", entao precisa estar espelhado na raiz de vendor/ tambem.
    root_logo = PLUGIN_ROOT / "logo.png"
    if root_logo.exists():
        shutil.copy(root_logo, DIST / "vendor" / "logo.png")
        print("  [logo vendorizada] logo.png")

    # Mockups (*.html) vivem no mesmo nível de main.html (ui/templates/) - ver nota
    # no topo do arquivo sobre por que não é .../panels/. vendor_css_dst já criou
    # ui/templates/css/ dentro de dist/vendor/; aqui só copiamos os *.html por cima,
    # como irmãos da pasta css/.
    mockups_src = DOCS_SITE / "vendor_mockups" / "ui" / "templates"
    vendor_templates_dst = DIST / "vendor" / "ui" / "templates"
    for mockup_file in mockups_src.glob("*.html"):
        shutil.copy(mockup_file, vendor_templates_dst / mockup_file.name)
        print(f"  [mockup] {mockup_file.name}")


def copy_docs_assets():
    dst = DIST / "assets"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(DOCS_SITE / "assets", dst)
    print("  [assets] docs.css e imagens próprias do manual")


def build_pages():
    head_template = read(DOCS_SITE / "partials" / "head.html")
    footer_html = read(DOCS_SITE / "partials" / "footer.html")

    for page_id, title in PAGES:
        content = read(DOCS_SITE / "pages" / f"{page_id}.html")
        head = head_template.replace("{{TITLE}}", title)
        nav = build_nav(page_id)
        html = (
            f"{head}\n{nav}\n"
            f'<main class="doc-main">\n{content}\n</main>\n'
            f"{footer_html}\n</body>\n</html>\n"
        )
        (DIST / f"{page_id}.html").write_text(html, encoding="utf-8")
        print(f"  [página] {page_id}.html")


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    print("Vendorizando CSS/imagens reais do plugin...")
    vendor_assets()
    print("Copiando assets próprios do manual...")
    copy_docs_assets()
    print("Montando páginas...")
    build_pages()

    print(f"\nPronto: {DIST}")
    print("Suba o conteúdo de dist/ para o bucket do MinIO.")


if __name__ == "__main__":
    main()

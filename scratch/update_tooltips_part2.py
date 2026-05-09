import os

files = [
    'ui/templates/panels/editor.html',
    'editando.html'
]

replacements = {
    'id="proc-mf-sigla" type="text"': 'id="proc-mf-sigla" type="text" title="Sigla do órgão. Ex: SMA, INPE, IBGE."',
    'id="meta-mf-sigla" type="text"': 'id="meta-mf-sigla" type="text" title="Sigla do órgão. Ex: SMA, INPE, IBGE."',
    'id="proc-mf-org" type="text"': 'id="proc-mf-org" type="text" title="Nome corporativo extenso do órgão."',
    'id="meta-mf-org" type="text"': 'id="meta-mf-org" type="text" title="Nome corporativo extenso do órgão."',
    
    # EPSG titles
    '<option value="EPSG:4674">EPSG:4674 - SIRGAS 2000</option>': '<option value="EPSG:4674" title="SIRGAS 2000 - Sistema de Referência Geocêntrico Oficial do Brasil">EPSG:4674 - SIRGAS 2000</option>',
    '<option value="EPSG:31982">EPSG:31982 - SIRGAS 2000 / UTM 22S</option>': '<option value="EPSG:31982" title="SIRGAS 2000 Projetado / UTM Zona 22S - Abrange o Oeste de SP">EPSG:31982 - SIRGAS 2000 / UTM 22S</option>',
    '<option value="EPSG:31983">EPSG:31983 - SIRGAS 2000 / UTM 23S</option>': '<option value="EPSG:31983" title="SIRGAS 2000 Projetado / UTM Zona 23S - Abrange o Leste de SP">EPSG:31983 - SIRGAS 2000 / UTM 23S</option>',
    '<option value="EPSG:4326">EPSG:4326 - WGS 84</option>': '<option value="EPSG:4326" title="WGS 84 - Sistema de Coordenadas Geográficas Global (Padrão GPS/Web)">EPSG:4326 - WGS 84</option>',
    '<option value="EPSG:4618">EPSG:4618 - SAD69</option>': '<option value="EPSG:4618" title="SAD69 - Sistema de Referência Antigo">EPSG:4618 - SAD69</option>',
    
    # Further inputs
    'id="f-epsgTitle" type="text" placeholder="ex: SIRGAS 2000 (EPSG:4674)"': 'id="f-epsgTitle" type="text" placeholder="ex: SIRGAS 2000 (EPSG:4674)" title="Nome formatado do SRC. Será preenchido automaticamente ao selecionar o EPSG acima."',
    'id="f-edition" type="number" value="0" min="0" oninput="toggleEditionDate(this.value)"': 'id="f-edition" type="number" value="0" min="0" oninput="toggleEditionDate(this.value)" title="Versão numérica do conjunto de dados."',
    'id="f-thumbnail_url" type="text" placeholder="https://..."': 'id="f-thumbnail_url" type="text" placeholder="https://..." title="Cole o link de uma imagem hospedada na web que represente bem estes dados."',
    'id="f-northBoundLatitude" type="number"': 'id="f-northBoundLatitude" type="number" title="Coordenada Y máxima (Latitude) em graus decimais."',
    'id="f-southBoundLatitude" type="number"': 'id="f-southBoundLatitude" type="number" title="Coordenada Y mínima (Latitude) em graus decimais."',
    'id="f-eastBoundLongitude" type="number"': 'id="f-eastBoundLongitude" type="number" title="Coordenada X máxima (Longitude) em graus decimais."',
    'id="f-westBoundLongitude" type="number"': 'id="f-westBoundLongitude" type="number" title="Coordenada X mínima (Longitude) em graus decimais."',
    'id="f-spatialResolution_denominator" type="text" placeholder="ex: 25000"': 'id="f-spatialResolution_denominator" type="text" placeholder="ex: 25000" title="Exemplo: Digite apenas 25000 para uma escala de 1:25.000."'
}

for filepath in files:
    if not os.path.exists(filepath):
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    for old, new in replacements.items():
        if old in content and new not in content:
            content = content.replace(old, new)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated {filepath} part 2")

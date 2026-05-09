import re
import os

main_html_path = 'ui/templates/main.html'
styles_css_path = 'ui/templates/css/styles.css'
editando_html_path = 'editando.html'

# 1. New HTML for the navbar
# We will replace <header class="navbar"> ... </header> in both main.html and editando.html

new_header_html = """    <header class="navbar">
        <div class="nav-left">
            <button id="logo-btn" class="logo-link" onclick="bridge.navigate('home')">
                <img src="../../logo.png" alt="CDHU" class="logo-img">
            </button>
            
            <div class="dropdown">
                <button class="dropbtn">
                    <span>Arquivo</span>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="4" stroke="currentColor" class="chevron-icon">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5"></path>
                    </svg>
                </button>
                <div class="dropdown-content">
                    <a href="#" onclick="trySaveMetadata()">Continuar depois</a>
                    <a href="#" onclick="tryExportXml()">Exportar .xml</a>
                </div>
            </div>
            
            <div class="dropdown">
                <button class="dropbtn">
                    <span>Catálogo Geohab</span>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="4" stroke="currentColor" class="chevron-icon">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5"></path>
                    </svg>
                </button>
                <div class="dropdown-content">
                    <a href="#" onclick="navigate('editor')">Editar Metadados</a>
                    <a href="#" onclick="tryExportGeohab()">Publicar no Catálogo</a>
                </div>
            </div>
            
            <div class="dropdown">
                <button class="dropbtn">
                    <span>GeoServer</span>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="4" stroke="currentColor" class="chevron-icon">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5"></path>
                    </svg>
                </button>
                <div class="dropdown-content">
                    <a href="#" onclick="bridge.navigate('geoserver')">Publicar Camada</a>
                </div>
            </div>
        </div>

        <div class="nav-right">
            <div id="layer-badge" class="layer-badge" style="display:none" title="Camada ativa no QGIS">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                    <polyline points="2 17 12 22 22 17"/>
                    <polyline points="2 12 12 17 22 12"/>
                </svg>
                <span id="layer-badge-name"></span>
            </div>
            <div id="user-info" class="user-badge" style="display: none;" onclick="doLogout()" title="Clique para sair">
                <span class="user-name">Usuário</span>
                <div class="status-dot"></div>
            </div>
            <button id="login-btn" class="btn btn-login" onclick="navigate('login')">Entrar</button>
        </div>
    </header>"""

def replace_header(filepath):
    if not os.path.exists(filepath): return
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # regex to find <header class="navbar"> ... </header>
    pattern = re.compile(r'<header class="navbar">.*?</header>', re.DOTALL)
    html = pattern.sub(new_header_html, html)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

replace_header(main_html_path)
replace_header(editando_html_path)

# 2. Update CSS in styles.css and editando.html
new_css_block = """/* NAVBAR CDHU SYSTEM STYLE */
.navbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background-color: #ffffff;
    height: 56px;
    border-bottom: 1px solid var(--border);
    color: #475569;
    font-size: 14px;
}

.nav-left, .nav-right {
    display: flex;
    align-items: center;
    height: 100%;
}

.logo-link {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 8px 32px;
    background-color: #000000;
    border-radius: 0 8px 8px 0;
    height: 100%;
    cursor: pointer;
    border: none;
    margin-right: 24px;
}

.logo-img {
    width: 128px;
    filter: brightness(0) invert(1); /* Ensure it's white if not already */
}

.dropdown {
    position: relative;
    display: inline-flex;
    height: 100%;
    align-items: center;
}

.dropbtn {
    display: flex;
    align-items: center;
    gap: 4px;
    background-color: transparent;
    color: #475569;
    padding: 0 16px;
    font-size: 14px;
    font-weight: 600;
    border: none;
    cursor: pointer;
    height: 100%;
    transition: color 0.2s;
}

.dropbtn:hover {
    color: var(--accent, #e11d48);
}

.chevron-icon {
    width: 14px;
    height: 14px;
    transition: transform 0.2s ease;
}

.dropdown:hover .chevron-icon {
    transform: rotate(180deg);
}

.dropdown-content {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    background-color: #ffffff;
    min-width: 200px;
    box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1);
    border: 1px solid rgba(0,0,0,0.05);
    border-radius: 12px;
    padding: 6px;
    z-index: 1002;
    opacity: 0;
    visibility: hidden;
    transform: translateY(8px);
    transition: all 0.2s ease-out;
    display: flex;
    flex-direction: column;
}

.dropdown:hover .dropdown-content {
    opacity: 1;
    visibility: visible;
    transform: translateY(0);
}

.dropdown-content a {
    color: #475569;
    padding: 8px 12px;
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 8px;
    border-radius: 6px;
    font-weight: 500;
    font-size: 14px;
    transition: all 0.15s;
}

.dropdown-content a:hover {
    background-color: #fff1f2;
    color: var(--accent, #e11d48);
}
"""

def replace_css(filepath):
    if not os.path.exists(filepath): return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We will replace the entire /* HEADER */ section up to /* BUTTONS */
    # Find the bounds
    start_idx = content.find('/* HEADER */')
    end_idx = content.find('/* BUTTONS */')
    
    if start_idx != -1 and end_idx != -1:
        new_content = content[:start_idx] + new_css_block + '\n' + content[end_idx:]
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

replace_css(styles_css_path)
replace_css(editando_html_path)

print("Header update applied successfully")

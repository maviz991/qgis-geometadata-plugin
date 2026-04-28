# styles.py
import os

def get_stylesheet(img_dir: str) -> str:
    """
    Retorna o QSS completo do plugin, lendo do arquivo styles.css.
    img_dir: caminho absoluto para a pasta img/ (forward-slashes).
    """
    img = img_dir.replace("\\", "/")
    
    # --- Variáveis de cor (alterar aqui muda globalmente) ---
    accent = "#e5222d"          # cor principal (vermelho CDHU)
    accent_hover = "#c0111b"    # hover mais escuro
    accent_light = "#fef2f2"    # fundo leve de destaque

    # Caminho do arquivo CSS
    current_dir = os.path.dirname(__file__)
    css_path = os.path.join(current_dir, "styles.css")
    
    if not os.path.exists(css_path):
        return ""
        
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
        
    # Substitui variáveis dinâmicas. 
    # No CSS usamos VAR_ACCENT, VAR_IMG, etc. 
    # Delimitadores sem chaves evitam mangling por formatadores CSS.
    variables = {
        "VAR_ACCENT": accent,
        "VAR_ACCENT_HOVER": accent_hover,
        "VAR_ACCENT_LIGHT": accent_light,
        "VAR_IMG": img
    }
    
    for key, value in variables.items():
        css = css.replace(key, value)
        
    return css

# Compatibilidade retroativa
STYLE_SHEET = get_stylesheet(":/plugins/geometadata/img")

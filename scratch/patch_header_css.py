import re
import os

styles_css_path = 'ui/templates/css/styles.css'

new_css_block = """/* NAVBAR */
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
    filter: brightness(0) invert(1);
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
    
    start_idx = content.find('/* NAVBAR */')
    end_idx = content.find('/* BUTTONS */')
    
    if start_idx != -1 and end_idx != -1:
        new_content = content[:start_idx] + new_css_block + '\n' + content[end_idx:]
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Successfully patched {filepath}")
    else:
        print(f"Could not find markers in {filepath}")

replace_css(styles_css_path)

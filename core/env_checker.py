# -*- coding: utf-8 -*-
"""
env_checker.py — GeoMetadata Plugin
=====================================
Verifica a disponibilidade das dependências externas do plugin.
Consultado antes de qualquer instalação para evitar trabalho desnecessário.
"""

import sys
import os
import site
from typing import List

# Trava global para evitar múltiplos SetupDialogs abertos simultaneamente
_setup_dialog_open = False

# ---------------------------------------------------------------------------
# FIX: Injeção de Path para Windows User Site-Packages
# ---------------------------------------------------------------------------
# No Windows, instalações 'pip install --user' ficam em AppData, que às vezes
# não está no sys.path do QGIS. Forçamos a inclusão para evitar loops de instalação.
if os.name == 'nt':
    user_site = site.getusersitepackages()
    if user_site not in sys.path and os.path.exists(user_site):
        sys.path.append(user_site)


def is_msal_available() -> bool:
    try:
        import msal  # noqa: F401
        return True
    except ImportError:
        return False


def is_webengine_available() -> tuple:
    """
    Retorna (bool, error_message).
    Verifica se o WebEngine pode ser importado.
    """
    # Tenta vários caminhos de importação comuns no QGIS
    import_errors = []
    
    # 1. Via qgis.PyQt
    try:
        from qgis.PyQt.QtWebEngineWidgets import QWebEngineView # noqa
        return True, ""
    except Exception as e:
        import_errors.append(f"qgis.PyQt: {str(e)}")

    # 2. Via PyQt5 direto
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView # noqa
        return True, ""
    except Exception as e:
        import_errors.append(f"PyQt5 direct: {str(e)}")

    # Se chegamos aqui, falhou. Analisamos o erro mais relevante.
    last_err = import_errors[-1]
    
    # Se o erro for sobre inicialização (OpenGL), consideramos que EXISTE.
    if "AA_ShareOpenGLContexts" in last_err or "instance is created" in last_err:
        return True, ""
        
    return False, last_err


def missing_packages() -> List[str]:
    """
    Retorna lista de pacotes pip que precisam ser instalados.
    """
    pkgs: List[str] = []
    
    if not is_msal_available():
        pkgs.append("msal")
        print("GeoMetadata: msal está FALTANDO.")
    else:
        print("GeoMetadata: msal detectado com SUCESSO.")
        
    available, error = is_webengine_available()
    if not available:
        # Só consideramos falta real se o erro for explicitamente de módulo inexistente
        if "No module named" in error:
            pkgs.append("PyQtWebEngine")
            print(f"GeoMetadata: PyQtWebEngine está FALTANDO. Erro: {error}")
        else:
            # Erro de DLL ou inicialização: consideramos presente mas alertamos
            print(f"GeoMetadata: PyQtWebEngine detectado mas com erro de carregamento: {error}")
    else:
        print("GeoMetadata: PyQtWebEngine detectado com SUCESSO.")
            
    return pkgs


def check_and_run_setup(parent=None):
    """
    Verifica se há pacotes faltando e abre o SetupDialog de forma segura
    (evitando duplicatas).
    """
    global _setup_dialog_open
    
    if _setup_dialog_open:
        return False
        
    pkgs = missing_packages()
    if not pkgs:
        return True
        
    _setup_dialog_open = True
    try:
        from ..ui.setup_dialog import SetupDialog
        dlg = SetupDialog(pkgs, parent=parent)
        dlg.exec_()
        # Após o exec, verificamos novamente se ainda falta algo
        return not bool(missing_packages())
    finally:
        _setup_dialog_open = False

# Rótulos amigáveis exibidos na SetupDialog
PACKAGE_LABELS = {
    "msal":          "Login corporativo",
    "PyQtWebEngine": "Interface visual nativa",
}

# -*- coding: utf-8 -*-
"""
env_checker.py - GeoMetadata Plugin
=====================================
Verifica a disponibilidade das dependências externas do plugin.
Consultado antes de qualquer instalação para evitar trabalho desnecessário.
"""

import sys
import os
import site
import logging
from typing import List

log = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Fix silencioso: lxml 5.2.1 tem um bug de empacotamento do wheel Windows que
# causa crash nativo (access violation em xmlDictReference) ao construir XML
# - ver qgis/QGIS#58205. Corrigido na 5.2.2+. Atualizamos em background sem
# incomodar o usuário; só é aplicado depois que o QGIS for reiniciado (módulo
# nativo já carregado na sessão atual não pode ser trocado a quente).
_LXML_SAFE_MIN_VERSION = (5, 2, 2)
_lxml_fix_attempted = False
_lxml_installer_ref = None  # mantém a QThread viva enquanto roda em background


def _lxml_version_tuple():
    try:
        import lxml
        return tuple(int(p) for p in lxml.__version__.split('.')[:3])
    except Exception:
        return None


def is_lxml_safe() -> bool:
    """False somente quando a versão instalada é conhecidamente afetada pelo bug."""
    version = _lxml_version_tuple()
    if version is None:
        return True
    return version >= _LXML_SAFE_MIN_VERSION


def silently_fix_lxml_if_needed():
    """Dispara `pip install --user --upgrade lxml>=5.2.2` em background, sem
    diálogo nem aviso, se a versão instalada tiver o bug de crash conhecido.
    Roda no máximo uma vez por sessão do QGIS."""
    global _lxml_fix_attempted, _lxml_installer_ref
    if _lxml_fix_attempted or is_lxml_safe():
        return
    _lxml_fix_attempted = True

    from .dependency_installer import DependencyInstaller
    installer = DependencyInstaller(
        f"lxml>={'.'.join(map(str, _LXML_SAFE_MIN_VERSION))}",
        extra_args=["--upgrade", "--user"]
    )
    def _release_ref():
        global _lxml_installer_ref
        _lxml_installer_ref = None

    installer.install_success.connect(
        lambda pkg: log.info("GeoMetadata: %s atualizado em background (efetivo após reiniciar o QGIS).", pkg)
    )
    installer.install_failed.connect(
        lambda pkg, err: log.warning("GeoMetadata: falha ao atualizar %s em background: %s", pkg, err)
    )
    installer.finished.connect(_release_ref)
    _lxml_installer_ref = installer
    installer.start()


def silently_install_ca_if_needed():
    """Instala o certificado CA corporativo da CDHU no bundle do certifi
    (via core/ca_installer.py), se ainda não estiver instalado. Roda em
    background (thread principal - operação de arquivo local, sem rede).
    Segura chamar mais de uma vez: ca_installer é idempotente."""
    try:
        from .ca_installer import install_ca_cert, is_ca_cert_available
        if is_ca_cert_available():
            install_ca_cert()
    except Exception as exc:
        log.warning("GeoMetadata [env_checker] falha ao instalar CA corporativa: %s", exc)


def missing_packages() -> List[str]:
    """
    Retorna lista de pacotes pip que precisam ser instalados.
    """
    pkgs: List[str] = []

    # msal não é mais necessário: o login SSO passou a usar a sessão do próprio
    # gateway georchestra (QWebEngineView embutida + cookie), não Bearer JWT
    # direto do Azure AD - ver ui/gateway_login_dialog.py. Deixado comentado (não
    # removido) pro caso do Geohab um dia passar a aceitar Bearer de terceiros
    # (Resource Server), quando esse fluxo via msal voltaria a fazer sentido.
    # if not is_msal_available():
    #     pkgs.append("msal")
    #     print("GeoMetadata: msal está FALTANDO.")
    # else:
    #     print("GeoMetadata: msal detectado com SUCESSO.")

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
    # "msal":        "Login corporativo",  # ver comentário em missing_packages()
    "PyQtWebEngine": "Interface visual nativa",
    "certifi":       "Certificados TLS corporativos",
}

# -*- coding: utf-8 -*-
import os
import sys
import subprocess
from typing import List
from qgis.PyQt.QtCore import QThread, pyqtSignal


def _find_python_executable() -> str:
    """
    Localiza o python.exe correto no ambiente QGIS.
    No Windows, sys.prefix aponta para o diretório raiz do Python 
    (ex: C:\Program Files\QGIS 3.34\apps\Python312).
    """
    # 1. Se sys.executable for um python.exe (e não qgis.exe), usamos ele direto
    if sys.executable.lower().endswith("python.exe") or sys.executable.lower().endswith("pythonw.exe"):
        return sys.executable

    # 2. Candidatos baseados em sys.prefix (padrão OSGeo4W / QGIS Windows)
    candidates = [
        os.path.join(sys.prefix, "python.exe"),
        os.path.join(sys.prefix, "bin", "python3"), # Linux/Mac
        os.path.join(sys.prefix, "python3.exe"),
    ]
    
    # 3. Fallback para sys.exec_prefix
    if hasattr(sys, 'exec_prefix'):
        candidates.append(os.path.join(sys.exec_prefix, "python.exe"))

    for path in candidates:
        if path and os.path.isfile(path):
            return path
            
    return sys.executable


class DependencyInstaller(QThread):
    """Instala um pacote pip em thread de background sem bloquear a UI."""

    install_success = pyqtSignal(str)       # nome do pacote
    install_failed  = pyqtSignal(str, str)  # nome do pacote, mensagem de erro

    def __init__(self, package: str, parent=None, extra_args=None):
        super().__init__(parent)
        self._package = package
        self._extra_args = extra_args or []

    def run(self):
        python = _find_python_executable()
        # No Windows, impede abertura de janela de console (tela preta)
        creation_flags = 0
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NO_WINDOW

        try:
            result = subprocess.run(
                [python, "-m", "pip", "install", self._package, "--quiet"] + self._extra_args,
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=creation_flags
            )
            if result.returncode == 0:
                self.install_success.emit(self._package)
            else:
                error = (result.stderr or result.stdout or "Erro desconhecido").strip()
                self.install_failed.emit(self._package, error)
        except subprocess.TimeoutExpired:
            self.install_failed.emit(self._package, "Tempo limite excedido (5 min).")
        except Exception as e:
            self.install_failed.emit(self._package, str(e))


# ---------------------------------------------------------------------------
# Instalador de múltiplos pacotes - sequencial com progresso por pacote
# ---------------------------------------------------------------------------
class MultiPackageInstaller(QThread):
    """
    Instala uma lista de pacotes pip em sequência, emitindo sinais de progresso
    por pacote. Interrompe na primeira falha.
    """

    package_started  = pyqtSignal(str)      # nome do pacote iniciando
    package_done     = pyqtSignal(str)       # nome do pacote concluído
    package_failed   = pyqtSignal(str, str)  # nome do pacote, mensagem de erro
    progress_updated = pyqtSignal(int, int)  # (concluídos, total)
    all_done         = pyqtSignal()          # todos instalados com sucesso

    def __init__(self, packages: List[str], parent=None):
        super().__init__(parent)
        self._packages = list(packages)

    def run(self):
        total  = len(self._packages)
        python = _find_python_executable()
        
        # No Windows, impede abertura de janela de console (tela preta)
        creation_flags = 0
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NO_WINDOW

        for idx, pkg in enumerate(self._packages):
            self.package_started.emit(pkg)
            self.progress_updated.emit(idx, total)
            try:
                result = subprocess.run(
                    [python, "-m", "pip", "install", pkg, "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    creationflags=creation_flags
                )
                if result.returncode == 0:
                    self.package_done.emit(pkg)
                else:
                    error = (result.stderr or result.stdout or "Erro desconhecido").strip()
                    self.package_failed.emit(pkg, error)
                    return
            except subprocess.TimeoutExpired:
                self.package_failed.emit(pkg, "Tempo limite excedido (5 min).")
                return
            except Exception as e:
                self.package_failed.emit(pkg, str(e))
                return

        self.progress_updated.emit(total, total)
        self.all_done.emit()

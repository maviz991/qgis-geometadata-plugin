# -*- coding: utf-8 -*-
import os
import sys
import subprocess
from qgis.PyQt.QtCore import QThread, pyqtSignal


def _find_python_executable() -> str:
    """
    Localiza o python.exe correto no ambiente QGIS.

    No Windows, sys.executable aponta para qgis.exe (não python.exe).
    sys.prefix aponta para o diretório raiz do Python (ex: C:\\QGIS\\apps\\Python39),
    que é confiável em todas as instalações OSGeo4W.
    """
    candidates = [
        # Windows OSGeo4W: Python fica em sys.prefix\python.exe
        os.path.join(sys.prefix, "python.exe"),
        os.path.join(sys.prefix, "python3.exe"),
        # Fallback: sys.exec_prefix
        os.path.join(sys.exec_prefix, "python.exe"),
        os.path.join(sys.exec_prefix, "python3.exe"),
        # Linux / Mac: binário na mesma pasta do executável
        os.path.join(os.path.dirname(sys.executable), "python3"),
        os.path.join(os.path.dirname(sys.executable), "python3.exe"),
        os.path.join(os.path.dirname(sys.executable), "python.exe"),
        # Último recurso
        sys.executable,
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return sys.executable


class DependencyInstaller(QThread):
    """Instala um pacote pip em thread de background sem bloquear a UI."""

    install_success = pyqtSignal(str)       # nome do pacote
    install_failed  = pyqtSignal(str, str)  # nome do pacote, mensagem de erro

    def __init__(self, package: str, parent=None):
        super().__init__(parent)
        self._package = package

    def run(self):
        python = _find_python_executable()
        try:
            result = subprocess.run(
                [python, "-m", "pip", "install", self._package, "--quiet"],
                capture_output=True,
                text=True,
                timeout=300  # 5 min: redes corporativas podem ser lentas
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

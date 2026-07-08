# -*- coding: utf-8 -*-
"""
setup_dialog.py — GeoMetadata Plugin
=====================================
Tela de boas-vindas / preparação de ambiente.
Exibida na primeira carga quando dependências estão ausentes.
Construída em QSS puro (sem PyQtWebEngine) para funcionar sempre.
"""

import os

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QWidget, QFrame
)
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QPixmap, QColor, QPalette

from ..core.env_checker import PACKAGE_LABELS
from ..core.dependency_installer import MultiPackageInstaller
from ..core.plugin_config import config_loader

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(__file__))
_LOGO_PATH   = os.path.join(_PLUGIN_ROOT, "img", "logo.png")
_ACCENT      = "#e5222d"

# Ícones de estado (texto puro — sem emoji exige suporte de fonte)
_ICON_WAIT  = "○"
_ICON_RUN   = "▶"
_ICON_OK    = "✓"
_ICON_FAIL  = "✗"


def _is_dark_theme() -> bool:
    from qgis.PyQt.QtWidgets import QApplication
    bg = QApplication.palette().color(QPalette.Window)
    return bg.lightness() < 128


class SetupDialog(QDialog):
    """
    Diálogo de preparação de ambiente.

    Recebe a lista de pacotes que precisam ser instalados e orquestra
    a instalação via MultiPackageInstaller, exibindo progresso por pacote.

    Uso:
        dlg = SetupDialog(["msal", "PyQtWebEngine"], parent=iface.mainWindow())
        dlg.exec_()
    """

    def __init__(self, packages: list, parent=None):
        super().__init__(parent)
        self._packages  = packages
        self._installer = None
        self._row_widgets: dict = {}   # pkg -> (icon_lbl, text_lbl)
        self._dark = _is_dark_theme()

        self.setWindowTitle("GeoMetadata — Preparando ambiente")
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowTitleHint |
            Qt.CustomizeWindowHint
        )
        self.setFixedWidth(420)
        self.setStyleSheet(self._stylesheet())

        self._build_ui()
        self._start_install()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 28)
        root.setSpacing(0)

        # Logo
        logo = QLabel()
        pix  = QPixmap(_LOGO_PATH)
        if not pix.isNull():
            logo.setPixmap(pix.scaledToHeight(56, Qt.SmoothTransformation))
        else:
            logo.setText("<b style='font-size:22px;color:#e5222d;'>GEOHAB</b>")
            logo.setTextFormat(Qt.RichText)
        logo.setAlignment(Qt.AlignCenter)
        root.addWidget(logo)
        root.addSpacing(20)

        # Título
        title = QLabel("Bem-vindo ao Geohab Plugin")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)
        root.addSpacing(4)

        # Subtítulo
        sub = QLabel("Preparando o ambiente para o primeiro uso...")
        sub.setObjectName("Sub")
        sub.setAlignment(Qt.AlignCenter)
        root.addWidget(sub)
        root.addSpacing(24)

        # Card de pacotes
        card = QFrame()
        card.setObjectName("Card")
        card_lyt = QVBoxLayout(card)
        card_lyt.setContentsMargins(20, 16, 20, 16)
        card_lyt.setSpacing(10)

        hdr = QLabel("Instalando dependências:")
        hdr.setObjectName("CardHdr")
        card_lyt.addWidget(hdr)

        for pkg in self._packages:
            row     = QHBoxLayout()
            row.setSpacing(10)
            ico_lbl = QLabel(_ICON_WAIT)
            ico_lbl.setObjectName("IcoWait")
            ico_lbl.setFixedWidth(16)
            txt_lbl = QLabel(PACKAGE_LABELS.get(pkg, pkg))
            txt_lbl.setObjectName("PkgText")
            row.addWidget(ico_lbl)
            row.addWidget(txt_lbl, 1)
            card_lyt.addLayout(row)
            self._row_widgets[pkg] = (ico_lbl, txt_lbl)

        root.addWidget(card)
        root.addSpacing(16)

        # Barra de progresso
        self._prog = QProgressBar()
        self._prog.setRange(0, len(self._packages))
        self._prog.setValue(0)
        self._prog.setTextVisible(False)
        self._prog.setFixedHeight(6)
        root.addWidget(self._prog)
        root.addSpacing(14)

        # Status geral
        self._status_lbl = QLabel("Verificando ambiente...")
        self._status_lbl.setObjectName("StatusLbl")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setOpenExternalLinks(True)
        self._status_lbl.setTextInteractionFlags(Qt.TextBrowserInteraction)
        root.addWidget(self._status_lbl)
        root.addSpacing(20)

        # Botão (inicialmente oculto)
        self._btn = QPushButton("Fechar")
        self._btn.setObjectName("Btn")
        self._btn.setMinimumHeight(40)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self.accept)
        self._btn.setVisible(False)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Instalação
    # ------------------------------------------------------------------

    def _start_install(self):
        self._installer = MultiPackageInstaller(self._packages, parent=self)
        self._installer.package_started.connect(self._on_pkg_start)
        self._installer.package_done.connect(self._on_pkg_done)
        self._installer.package_failed.connect(self._on_pkg_fail)
        self._installer.progress_updated.connect(self._on_progress)
        self._installer.all_done.connect(self._on_all_done)
        self._installer.start()

    def _on_pkg_start(self, pkg: str):
        ico, txt = self._row_widgets[pkg]
        ico.setObjectName("IcoRun")
        ico.setText(_ICON_RUN)
        ico.style().unpolish(ico)
        ico.style().polish(ico)
        self._status_lbl.setText(f"Instalando {PACKAGE_LABELS.get(pkg, pkg)}...")

    def _on_pkg_done(self, pkg: str):
        ico, _ = self._row_widgets[pkg]
        ico.setObjectName("IcoOk")
        ico.setText(_ICON_OK)
        ico.style().unpolish(ico)
        ico.style().polish(ico)

    def _on_pkg_fail(self, pkg: str, error: str):
        ico, _ = self._row_widgets[pkg]
        ico.setObjectName("IcoFail")
        ico.setText(_ICON_FAIL)
        ico.style().unpolish(ico)
        ico.style().polish(ico)
        
        # Mensagem contextual para PyQtWebEngine
        cda_url = config_loader.get_cda_url()
        if "PyQtWebEngine" in pkg:
            msg = (
                f"Falha ao carregar a interface visual.\n\n"
                f"Isso ocorre por uma incompatibilidade do ambiente QGIS.\n"
                f"SOLUÇÃO: Abra um ticket no CDA (<a href='{cda_url}'>cda.cdhu.sp.gov.br</a>)."
            )
        else:
            msg = (
                "Falha ao configurar componente de login.<br><br>"
                "Por favor, entre em contato com o suporte técnico no "
                f"<a href='{cda_url}'>CDA (cda.cdhu.sp.gov.br)</a>."
            )

        short = error[:120] + "..." if len(error) > 120 else error
        self._status_lbl.setText(f"{msg}<br><br><b>Detalhe:</b> {short}")
        self._btn.setVisible(True)

    def _on_progress(self, done: int, total: int):
        self._prog.setValue(done)

    def _on_all_done(self):
        self._prog.setValue(len(self._packages))
        self._status_lbl.setText(
            "Instalação concluída!\n"
            "Reinicie o QGIS para ativar todos os recursos."
        )
        self._btn.setText("Fechar")
        self._btn.setVisible(True)

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    def _stylesheet(self) -> str:
        if self._dark:
            bg, fg, card_bg, card_border, sub_fg = (
                "#1e1e1e", "#e2e8f0", "#2a2a2a", "#3a3a3a", "#94a3b8"
            )
        else:
            bg, fg, card_bg, card_border, sub_fg = (
                "#ffffff", "#1e293b", "#f8fafc", "#e2e8f0", "#64748b"
            )

        return f"""
        QDialog {{
            background: {bg};
        }}
        #Title {{
            font-size: 16px;
            font-weight: 700;
            color: {fg};
        }}
        #Sub {{
            font-size: 12px;
            color: {sub_fg};
        }}
        #Card {{
            background: {card_bg};
            border: 1px solid {card_border};
            border-radius: 10px;
        }}
        #CardHdr {{
            font-size: 12px;
            font-weight: 600;
            color: {sub_fg};
        }}
        #PkgText {{
            font-size: 13px;
            color: {fg};
        }}
        #IcoWait {{ color: {sub_fg}; font-size: 14px; font-weight: 700; }}
        #IcoRun  {{ color: #f59e0b;  font-size: 14px; font-weight: 700; }}
        #IcoOk   {{ color: #16a34a;  font-size: 14px; font-weight: 700; }}
        #IcoFail {{ color: #dc2626;  font-size: 14px; font-weight: 700; }}
        #Status {{
            font-size: 12px;
            color: {sub_fg};
        }}
        QProgressBar {{
            background: {card_border};
            border: none;
            border-radius: 3px;
        }}
        QProgressBar::chunk {{
            background: {_ACCENT};
            border-radius: 3px;
        }}
        #Btn {{
            background: {_ACCENT};
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-weight: 700;
            font-size: 13px;
            padding: 0 28px;
        }}
        #Btn:hover {{ background: #c0111b; }}
        """

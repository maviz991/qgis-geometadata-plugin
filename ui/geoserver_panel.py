# -*- coding: utf-8 -*-
"""
GeoServerPanel - Painel de publicação GeoServer (Placeholder v2.0)

Exibe uma tela de boas-vindas com informações sobre o que estará
disponível neste painel na fase 2 do desenvolvimento.
"""

from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy
)
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QPixmap, QFont, QIcon


class GeoServerPanel(QWidget):
    """
    Painel placeholder para o módulo de publicação GeoServer.
    Será populado com os widgets reais de publicação na Fase 2.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GeoServerPanel")
        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Card centralizado
        root_layout.addStretch(1)
        root_layout.addWidget(self._build_card(), alignment=Qt.AlignCenter)
        root_layout.addStretch(1)

    def _build_card(self):
        card = QFrame()
        card.setObjectName("GeoServerPlaceholderCard")
        card.setFixedWidth(520)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(16)
        card_layout.setAlignment(Qt.AlignCenter)

        # Ícone
        icon_label = QLabel()
        icon_label.setObjectName("GeoServerIconLabel")
        pixmap = QPixmap(":/plugins/geometadata/img/geoserver_icon.png")
        if pixmap.isNull():
            # Fallback: emoji como texto
            icon_label.setText("🗄️")
            font = QFont()
            font.setPointSize(68)
            icon_label.setFont(font)
        else:
            icon_label.setPixmap(
                pixmap.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        icon_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(icon_label)

        # Título
        title = QLabel("GeoServer - Publicação de Camadas")
        title.setObjectName("GeoServerPlaceholderTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        card_layout.addWidget(title)

        # Subtítulo / descrição
        desc = QLabel(
            "Este painel permitirá publicar camadas vetoriais diretamente no GeoServer "
            "corporativo, exportar estilos SLD e gerenciar workspaces - sem sair do QGIS."
        )
        desc.setObjectName("GeoServerPlaceholderDesc")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("PlaceholderSeparator")
        card_layout.addWidget(sep)

        # Lista de funcionalidades em breve
        features = [
            ("📦", "Publicação lógica de camadas PostGIS (sem tráfego de dados)"),
            ("📤", "Upload de Shapefiles como arquivo ZIP"),
            ("🎨", "Exportação e vínculo de estilos SLD"),
            ("🗂️", "Listagem de workspaces e datastores"),
        ]

        for emoji, text in features:
            row = QHBoxLayout()
            row.setSpacing(10)

            icon_lbl = QLabel(emoji)
            icon_lbl.setObjectName("FeatureEmoji")
            icon_lbl.setFixedWidth(28)
            icon_lbl.setAlignment(Qt.AlignCenter)

            text_lbl = QLabel(text)
            text_lbl.setObjectName("FeatureText")
            text_lbl.setWordWrap(True)

            row.addWidget(icon_lbl)
            row.addWidget(text_lbl, 1)
            card_layout.addLayout(row)

        # Badge "Em breve"
        badge = QLabel("🚧  Em desenvolvimento - Fase 2")
        badge.setObjectName("ComingSoonBadge")
        badge.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(badge)

        return card

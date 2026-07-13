# -*- coding: utf-8 -*-
"""
HomePanel - Tela inicial do plugin GeoMetadata / Geohab.

Exibe cards para cada módulo disponível, permitindo navegação direta
para os painéis funcionais sem precisar usar o menu do header.
"""

from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QGridLayout, QSpacerItem
)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont, QPixmap


class HomePanel(QWidget):
    """
    Painel Home - ponto de entrada do plugin.

    Emite sinais para navegar aos painéis filhos:
      - navigate_geonetwork
      - navigate_geoserver
    """

    navigate_geonetwork = pyqtSignal()
    navigate_geoserver  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomePanel")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(0)

        # --- Cabeçalho da home ---
        root.addWidget(self._build_header())
        root.addSpacing(32)

        # --- Grade de cards ---
        root.addWidget(self._build_cards(), 1)
        root.addStretch()

    # ------------------------------------------------------------------
    def _build_header(self):
        container = QWidget()
        container.setObjectName("HomeTitleBar")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        title = QLabel("Bem-vindo ao Geohab Plugin")
        title.setObjectName("HomeTitle")

        subtitle = QLabel(
            "Selecione um módulo para começar. "
            "Utilize o menu no cabeçalho para acessar funções específicas."
        )
        subtitle.setObjectName("HomeSubtitle")
        subtitle.setWordWrap(True)

        lay.addWidget(title)
        lay.addWidget(subtitle)
        return container

    # ------------------------------------------------------------------
    def _build_cards(self):
        container = QWidget()
        container.setObjectName("HomeCardsContainer")
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(20)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        cards = [
            self._make_card(
                title       = "GeoNetwork",
                subtitle    = "Metadados MGB 2.0",
                description = (
                    "Crie, edite e publique metadados geoespaciais no padrão MGB 2.0. "
                    "Exporte para XML ou envie diretamente ao catálogo do Geohab."
                ),
                features    = [
                    "Formulário MGB 2.0 completo",
                    "Exportar / Importar XML",
                    "Publicar no catálogo",
                    "Associar camadas WMS/WFS",
                ],
                btn_label   = "Abrir GeoNetwork",
                btn_action  = self.navigate_geonetwork.emit,
                status      = "active",
                icon_text   = "🗂️",
            ),
            self._make_card(
                title       = "GeoServer",
                subtitle    = "Publicação de Camadas",
                description = (
                    "Publique camadas vetoriais diretamente no Geohab, "
                    "exporte estilos SLD e gerencie workspaces - sem sair do QGIS."
                ),
                features    = [
                    "Publicação lógica PostGIS",
                    "Upload de Shapefiles (ZIP)",
                    "Exportação de estilos SLD",
                    "Gestão de workspaces",
                ],
                btn_label   = "Em breve - Fase 2",
                btn_action  = self.navigate_geoserver.emit,
                status      = "soon",
                icon_text   = "🗄️",
            ),
        ]

        for col, card in enumerate(cards):
            grid.addWidget(card, 0, col)

        # Colunas de expansão iguais + coluna vazia para não esticar
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 2)  # espaço extra à direita

        return container

    # ------------------------------------------------------------------
    def _make_card(self, title, subtitle, description, features,
                   btn_label, btn_action, status, icon_text):
        """Cria um card de módulo."""
        card = QFrame()
        card.setObjectName(f"HomeCard_{status}")
        card.setProperty("cardStatus", status)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.setMaximumWidth(380)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 28, 28, 24)
        lay.setSpacing(0)

        # Ícone
        icon_lbl = QLabel(icon_text)
        icon_lbl.setObjectName("CardIcon")
        lay.addWidget(icon_lbl)
        lay.addSpacing(14)

        # Título
        title_lbl = QLabel(title)
        title_lbl.setObjectName("CardTitle")
        lay.addWidget(title_lbl)

        # Subtítulo / badge
        sub_lbl = QLabel(subtitle)
        sub_lbl.setObjectName(
            "CardSubtitle" if status == "active" else "CardSubtitleSoon"
        )
        lay.addWidget(sub_lbl)
        lay.addSpacing(14)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("CardSeparator")
        lay.addWidget(sep)
        lay.addSpacing(14)

        # Descrição
        desc_lbl = QLabel(description)
        desc_lbl.setObjectName("CardDescription")
        desc_lbl.setWordWrap(True)
        lay.addWidget(desc_lbl)
        lay.addSpacing(16)

        # Lista de funcionalidades
        for feat in features:
            row = QHBoxLayout()
            row.setSpacing(8)
            bullet = QLabel("•")
            bullet.setObjectName("CardBullet" if status == "active" else "CardBulletSoon")
            bullet.setFixedWidth(12)
            feat_lbl = QLabel(feat)
            feat_lbl.setObjectName("CardFeature")
            row.addWidget(bullet)
            row.addWidget(feat_lbl, 1)
            lay.addLayout(row)

        lay.addSpacing(24)
        lay.addStretch()

        # Botão de ação
        btn = QPushButton(btn_label)
        btn.setObjectName(
            "CardButton" if status == "active" else "CardButtonSoon"
        )
        btn.setCursor(Qt.PointingHandCursor)
        btn.setEnabled(status == "active")
        btn.clicked.connect(btn_action)
        lay.addWidget(btn)

        return card

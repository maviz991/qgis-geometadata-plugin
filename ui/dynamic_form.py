# -*- coding: utf-8 -*-
"""
Formulário dinâmico — layout com QTabWidget (abas).
Abas: Identificação | Contato | Extensão | Metadados
Atributos idênticos ao .ui original — FormManager não muda.
"""
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QTabWidget, QLabel, QLineEdit, QTextEdit,
    QComboBox, QSpinBox, QDateTimeEdit, QToolButton,
    QPushButton, QFrame, QSizePolicy
)
from qgis.PyQt.QtCore import Qt, QDateTime


# ---------------------------------------------------------------------------
# Helpers — campo com label acima
# ---------------------------------------------------------------------------

def _field(label_text, widget, required=False):
    w = QWidget()
    w.setObjectName("FieldWrapper")
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(5)
    suffix = "  <span style='color:#ef4444'>*</span>" if required else ""
    lbl = QLabel(f"{label_text}{suffix}")
    lbl.setObjectName("FieldLabel")
    v.addWidget(lbl)
    v.addWidget(widget)
    return w


def _f1(layout, label, widget, required=False):
    layout.addWidget(_field(label, widget, required))


def _f2(layout, lbl1, w1, lbl2, w2, req1=False, req2=False):
    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(_field(lbl1, w1, req1), 1)
    row.addWidget(_field(lbl2, w2, req2), 1)
    layout.addLayout(row)


def _tab_scroll(content_widget):
    """Envolve um widget numa QScrollArea para o conteúdo da aba."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setObjectName("TabScrollArea")
    scroll.setWidget(content_widget)
    return scroll


# ---------------------------------------------------------------------------
# Linha de contato
# ---------------------------------------------------------------------------

class _ContactRow(QWidget):
    def __init__(self, removable=True, parent=None):
        super().__init__(parent)
        self.setObjectName("ContactRow")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 3, 0, 3)
        h.setSpacing(8)

        self.field_org = QLineEdit()
        self.field_org.setObjectName("ContactCell")

        self.field_name = QLineEdit()
        self.field_name.setObjectName("ContactCell")

        self.field_email = QLineEdit()
        self.field_email.setObjectName("ContactCell")

        self.field_role = QComboBox()
        self.field_role.setObjectName("ContactCell")
        for text, data in [
            ('Dono', 'owner'), ('Autor', 'author'),
            ('Ponto de contato', 'pointOfContact'),
            ('Distribuidor', 'distributor'), ('Publicador', 'publisher'),
            ('Organizador', 'processor'), ('Originador', 'originator'),
        ]:
            self.field_role.addItem(text, data)

        h.addWidget(self.field_org, 3)
        h.addWidget(self.field_name, 2)
        h.addWidget(self.field_email, 3)
        h.addWidget(self.field_role, 2)

        if removable:
            btn = QPushButton("×")
            btn.setObjectName("RemoveContactButton")
            btn.setFixedSize(28, 28)
            btn.setToolTip("Remover contato")
            btn.clicked.connect(self._remove)
            h.addWidget(btn)
        else:
            sp = QWidget()
            sp.setFixedWidth(28)
            h.addWidget(sp)

    def _remove(self):
        self.setParent(None)
        self.deleteLater()

    def collect(self):
        return {
            'contact_organisationName': self.field_org.text(),
            'contact_individualName':   self.field_name.text(),
            'contact_email':            self.field_email.text(),
            'contact_role':             self.field_role.currentData(),
        }

    def populate(self, data):
        self.field_org.setText(data.get('contact_organisationName', ''))
        self.field_name.setText(data.get('contact_individualName', ''))
        self.field_email.setText(data.get('contact_email', ''))
        idx = self.field_role.findData(data.get('contact_role', ''))
        if idx >= 0:
            self.field_role.setCurrentIndex(idx)


# ---------------------------------------------------------------------------
# DynamicForm
# ---------------------------------------------------------------------------

class DynamicForm:
    """
    Formulário em QTabWidget.
    Abas: Identificação · Contato · Extensão Geográfica · Metadados
    """

    def __init__(self):
        self._extra_contact_rows = []
        self._build()

    def get_scroll_area(self):
        """Retorna o widget raiz (QTabWidget envolto num container)."""
        return self._root_widget

    # ------------------------------------------------------------------
    # Estrutura geral
    # ------------------------------------------------------------------

    def _build(self):
        self._root_widget = QWidget()
        self._root_widget.setObjectName("FormContainer")
        root_v = QVBoxLayout(self._root_widget)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("FormTabs")
        self._tabs.setDocumentMode(True)

        self._tabs.addTab(self._tab_identificacao(), "Identificação")
        self._tabs.addTab(self._tab_classificacao(), "Classificação")
        self._tabs.addTab(self._tab_extensao(),      "Extensão Geográfica")
        self._tabs.addTab(self._tab_metadados(),     "Metadados")

        root_v.addWidget(self._tabs)

        footer = self._build_footer()
        root_v.addWidget(footer)

    # ------------------------------------------------------------------
    # Aba 1 — Identificação (padrão GeoNetwork: id + contato na mesma tela)
    # ------------------------------------------------------------------

    def _tab_identificacao(self):
        content = QWidget()
        content.setObjectName("TabContent")
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(14)

        # --- Seção: Informações de Identificação ---
        lbl_id = QLabel("Informações de identificação")
        lbl_id.setObjectName("SubSectionLabel")
        lbl_id.setStyleSheet("font-size: 15px; font-weight: 700; padding: 0 0 4px 0;")
        v.addWidget(lbl_id)

        # Título
        self.lineEdit_title = QLineEdit()
        self.lineEdit_title.setPlaceholderText("Título da camada")
        _f1(v, "Título", self.lineEdit_title, required=True)

        # Data: [Tipo ▾] [Data 📅] [Hora 🕐]
        self.comboBox_date_type = QComboBox()
        self.comboBox_date_type.addItem("Criação", "creation")
        self.comboBox_date_type.addItem("Publicação", "publication")
        self.comboBox_date_type.addItem("Revisão", "revision")

        from qgis.PyQt.QtWidgets import QDateEdit, QTimeEdit
        self.dateEdit_date_creation = QDateEdit()
        self.dateEdit_date_creation.setDisplayFormat("dd/MM/yyyy")
        self.dateEdit_date_creation.setCalendarPopup(True)
        self.dateEdit_date_creation.setDate(QDateTime.currentDateTime().date())

        self.timeEdit_date_creation = QTimeEdit()
        self.timeEdit_date_creation.setDisplayFormat("HH:mm")
        self.timeEdit_date_creation.setTime(QDateTime.currentDateTime().time())

        # Monta a linha de Data com 3 colunas
        date_row = QHBoxLayout()
        date_row.setSpacing(8)
        date_row.addWidget(_field("Tipo", self.comboBox_date_type, required=True), 2)
        date_row.addWidget(_field("Data", self.dateEdit_date_creation, required=True), 3)
        date_row.addWidget(_field("Hora", self.timeEdit_date_creation), 2)
        v.addLayout(date_row)

        # Proxy oculto para manter compatibilidade com FormManager
        self.dateTimeEdit_date_creation = QDateTimeEdit()
        self.dateTimeEdit_date_creation.setVisible(False)
        v.addWidget(self.dateTimeEdit_date_creation)

        # Resumo (full-width)
        self.textEdit_abstract = QTextEdit()
        self.textEdit_abstract.setPlaceholderText(
            "Resumo descritivo da camada, geoprocessos aplicados, escala etc.")
        self.textEdit_abstract.setMinimumHeight(80)
        self.textEdit_abstract.setMaximumHeight(140)
        _f1(v, "Resumo", self.textEdit_abstract, required=True)

        # Status (full-width, sozinho)
        self.comboBox_status_codeListValue = QComboBox()
        _f1(v, "Status", self.comboBox_status_codeListValue, required=True)

        # --- Separador + Ponto de Contato ---
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setObjectName("TableDivider")
        v.addWidget(sep1)

        lbl_contact = QLabel("Ponto de Contato")
        lbl_contact.setObjectName("SubSectionLabel")
        lbl_contact.setStyleSheet("font-size: 14px; font-weight: 700; padding: 4px 0;")
        v.addWidget(lbl_contact)

        # Preset CDHU
        self.comboBox_contact_presets = QComboBox()
        self.comboBox_contact_presets.setToolTip(
            "Selecione um setor para preencher os campos automaticamente")
        _f1(v, "Preencher com setor CDHU", self.comboBox_contact_presets)

        # Cabeçalho da tabela
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr.setContentsMargins(0, 8, 28, 0)
        for col, stretch, req in [
            ("Nome da Organização", 3, False),
            ("Nome Individual", 2, True),
            ("Endereço Eletrônico", 3, False),
            ("Regra", 2, False),
        ]:
            sfx = "  <span style='color:#ef4444'>*</span>" if req else ""
            lbl = QLabel(f"{col}{sfx}")
            lbl.setObjectName("ContactColHeader")
            hdr.addWidget(lbl, stretch)
        v.addLayout(hdr)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setObjectName("TableDivider")
        v.addWidget(div)

        # Linha primária → FormManager
        self._primary_row = _ContactRow(removable=False)
        self.lineEdit_contact_organisationName = self._primary_row.field_org
        self.lineEdit_contact_individualName   = self._primary_row.field_name
        self.lineEdit_contact_email            = self._primary_row.field_email
        self.comboBox_contact_role             = self._primary_row.field_role
        v.addWidget(self._primary_row)

        # 2 linhas extras por padrão
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(4)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        for _ in range(2):
            row = _ContactRow(removable=True)
            self._rows_layout.addWidget(row)
            self._extra_contact_rows.append(row)
        v.addLayout(self._rows_layout)

        # Busca + [+]
        search_row = QHBoxLayout()
        self._contact_search = QLineEdit()
        self._contact_search.setPlaceholderText("Busque o contato")
        self._contact_search.setObjectName("ContactSearch")
        search_row.addWidget(self._contact_search, 1)
        btn_search = QPushButton("🔍︎")
        btn_search.setObjectName("SearchButton")
        btn_search.setFixedSize(34, 34)
        search_row.addWidget(btn_search)
        btn_add = QPushButton("+")
        btn_add.setObjectName("AddContactButton")
        btn_add.setFixedSize(34, 34)
        btn_add.clicked.connect(self._add_contact_row)
        search_row.addWidget(btn_add)
        v.addLayout(search_row)

        # --- Accordion: Detalhes de endereço (MGB 2.0) ---
        accordion = self._build_accordion("Detalhes de endereço (MGB 2.0)")
        acc_body = accordion["body"]
        acc_v = QVBoxLayout(acc_body)
        acc_v.setContentsMargins(16, 12, 16, 12)
        acc_v.setSpacing(12)

        self.lineEdit_contact_positionName = QLineEdit()
        self.lineEdit_contact_positionName.setPlaceholderText("Cargo | Posição")
        self.lineEdit_contact_phone = QLineEdit()
        self.lineEdit_contact_phone.setPlaceholderText("+55 11 0000-0000")
        _f2(acc_v, "Cargo", self.lineEdit_contact_positionName,
            "Telefone", self.lineEdit_contact_phone)

        self.lineEdit_contact_deliveryPoint = QLineEdit()
        self.lineEdit_contact_deliveryPoint.setPlaceholderText("Rua, nº, complemento")
        _f1(acc_v, "Endereço", self.lineEdit_contact_deliveryPoint, required=True)

        self.lineEdit_contact_city = QLineEdit()
        self.lineEdit_contact_city.setPlaceholderText("Cidade")
        self.comboBox_contact_administrativeArea = QComboBox()
        _f2(acc_v, "Cidade", self.lineEdit_contact_city,
            "Estado", self.comboBox_contact_administrativeArea, req1=True, req2=True)

        self.lineEdit_contact_postalCode = QLineEdit()
        self.lineEdit_contact_postalCode.setPlaceholderText("01014-930")
        self.lineEdit_contact_country = QLineEdit()
        self.lineEdit_contact_country.setPlaceholderText("Brasil")
        _f2(acc_v, "CEP", self.lineEdit_contact_postalCode,
            "País", self.lineEdit_contact_country, req1=True, req2=True)

        v.addWidget(accordion["widget"])

        v.addStretch()
        return _tab_scroll(content)

    def _build_accordion(self, title, expanded=False):
        """Cria um painel colapsável (accordion) estilo GeoNetwork."""
        section = QWidget()
        section.setObjectName("CollapsibleSection")
        section_v = QVBoxLayout(section)
        section_v.setContentsMargins(0, 0, 0, 0)
        section_v.setSpacing(0)

        header_btn = QPushButton(f"  ▶  {title}" if not expanded else f"  ▼  {title}")
        header_btn.setObjectName("CollapsibleHeader")
        header_btn.setCursor(Qt.PointingHandCursor)
        header_btn.setFixedHeight(30)
        section_v.addWidget(header_btn)

        body = QWidget()
        body.setObjectName("CollapsibleBody")
        body.setVisible(expanded)
        section_v.addWidget(body)

        def toggle():
            is_visible = body.isVisible()
            body.setVisible(not is_visible)
            header_btn.setText(f"  ▼  {title}" if not is_visible else f"  ▶  {title}")

        header_btn.clicked.connect(toggle)
        return {"widget": section, "body": body}

    # ------------------------------------------------------------------
    # Aba 2 — Classificação (campos técnicos)
    # ------------------------------------------------------------------

    def _tab_classificacao(self):
        content = QWidget()
        content.setObjectName("TabContent")
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        self.comboBox_MD_SpatialRepresentationTypeCode = QComboBox()
        self.comboBox_hierarchyLevel = QComboBox()
        _f2(v, "Tipo de Representação Espacial",
            self.comboBox_MD_SpatialRepresentationTypeCode,
            "Nível Hierárquico", self.comboBox_hierarchyLevel,
            req1=True, req2=True)

        self.comboBox_LanguageCode = QComboBox()
        self.comboBox_characterSet = QComboBox()
        _f2(v, "Idioma", self.comboBox_LanguageCode,
            "Codificação", self.comboBox_characterSet, req1=True)

        self.comboBox_topicCategory = QComboBox()
        _f1(v, "Categoria Temática", self.comboBox_topicCategory, required=True)

        self.lineEdit_textEdit_spatialResolution_denominator = QLineEdit()
        self.lineEdit_textEdit_spatialResolution_denominator.setPlaceholderText("Ex.: 1:5000 → 5000")
        self.lineEdit_MD_Keywords = QLineEdit()
        self.lineEdit_MD_Keywords.setPlaceholderText("Palavra-chave 1, Palavra-chave 2, ...")
        _f2(v, "Escala (denominador)",
            self.lineEdit_textEdit_spatialResolution_denominator,
            "Palavras-chave", self.lineEdit_MD_Keywords, req2=True)

        self.spinBox_edition = QSpinBox()
        self.spinBox_edition.setRange(1, 99)
        _f1(v, "Edição", self.spinBox_edition)

        self.lineEdit_thumbnail_url = QLineEdit()
        self.lineEdit_thumbnail_url.setPlaceholderText(
            "https://stor.cdhu.sp.gov.br/geo/publico/img.png")
        _f1(v, "URL Thumbnail", self.lineEdit_thumbnail_url)

        v.addStretch()
        return _tab_scroll(content)



    def _add_contact_row(self):
        row = _ContactRow(removable=True)
        text = self._contact_search.text().strip()
        if text:
            row.field_org.setText(text)
            self._contact_search.clear()
        self._rows_layout.addWidget(row)
        self._extra_contact_rows.append(row)

    def get_extra_contacts(self):
        return [r.collect() for r in self._extra_contact_rows
                if r.parent() and any(r.collect().values())]

    # ------------------------------------------------------------------
    # Aba 3 — Extensão Geográfica
    # ------------------------------------------------------------------

    def _tab_extensao(self):
        content = QWidget()
        content.setObjectName("TabContent")
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        self.lineEdit_northBoundLatitude = QLineEdit()
        self.lineEdit_northBoundLatitude.setPlaceholderText("Ex.: -23.40")
        self.lineEdit_southBoundLatitude = QLineEdit()
        self.lineEdit_southBoundLatitude.setPlaceholderText("Ex.: -24.00")
        _f2(v, "Norte", self.lineEdit_northBoundLatitude,
            "Sul", self.lineEdit_southBoundLatitude, req1=True, req2=True)

        self.lineEdit_westBoundLongitude = QLineEdit()
        self.lineEdit_westBoundLongitude.setPlaceholderText("Ex.: -47.20")
        self.lineEdit_eastBoundLongitude = QLineEdit()
        self.lineEdit_eastBoundLongitude.setPlaceholderText("Ex.: -46.30")
        _f2(v, "Oeste", self.lineEdit_westBoundLongitude,
            "Leste", self.lineEdit_eastBoundLongitude, req1=True, req2=True)

        v.addStretch()
        return content

    # ------------------------------------------------------------------
    # Aba 4 — Metadados (datas)
    # ------------------------------------------------------------------

    def _tab_metadados(self):
        content = QWidget()
        content.setObjectName("TabContent")
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        self.dateTimeEdit_dateStamp = QDateTimeEdit()
        self.dateTimeEdit_dateStamp.setDisplayFormat("dd/MM/yyyy HH:mm:ss")
        self.dateTimeEdit_dateStamp.setCalendarPopup(True)
        self.dateTimeEdit_dateStamp.setDateTime(QDateTime.currentDateTime())

        self.toolButton_set_today = QToolButton()
        self.toolButton_set_today.setText("Hoje")
        self.toolButton_set_today.setObjectName("TodayButton")
        self.toolButton_set_today.setToolTip("Definir para a data e hora atuais")

        stamp_w = QWidget()
        stamp_h = QHBoxLayout(stamp_w)
        stamp_h.setContentsMargins(0, 0, 0, 0)
        stamp_h.setSpacing(6)
        stamp_h.addWidget(self.dateTimeEdit_dateStamp, 1)
        stamp_h.addWidget(self.toolButton_set_today)

        _f1(v, "Data do Metadado", stamp_w)

        v.addStretch()
        return content

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    def _build_footer(self):
        w = QWidget()
        w.setObjectName("FooterBar")
        h = QHBoxLayout(w)
        h.setContentsMargins(16, 6, 16, 6)
        self.label_support_link = QLabel()
        self.label_support_link.setObjectName("label_support_link")
        h.addWidget(self.label_support_link)
        h.addStretch()
        self.label_2 = QLabel()
        h.addWidget(self.label_2)
        return w

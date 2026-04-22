import json
import re
import unicodedata
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt, QDateTime

class FormManager:
    """
    Controlador exclusivo do formulário de metadados.
    Responsabilidades: Coletar dados, injetar dados, validar marcações obrigatórias
    e gerenciar as caixas de seleção da Interface.
    """
    def __init__(self, ui, dialog_parent, contatos_predefinidos):
        self.ui = ui
        self.parent = dialog_parent
        self.contatos_predefinidos = contatos_predefinidos
        self.distribution_data = {'wms_data': {}, 'wfs_data': {}}
        self.current_metadata_uuid = None
        self._is_metadata_dirty = False

    def get_is_dirty(self):
        return self._is_metadata_dirty

    def set_is_dirty(self, state):
        self._is_metadata_dirty = state

    def validate_form(self):
        errors = []
        required_fields = {
            self.ui.lineEdit_title: "Título",
            self.ui.comboBox_status_codeListValue: "Status",
            self.ui.textEdit_abstract: "Resumo",
            self.ui.lineEdit_contact_individualName: "Sigla (Contato)",
            self.ui.lineEdit_contact_organisationName: "Nome da Organização (Contato)",
            self.ui.lineEdit_contact_deliveryPoint: "Endereço (Contato)",
            self.ui.lineEdit_contact_city: "Cidade (Contato)",
            self.ui.comboBox_contact_administrativeArea: "Estado (Contato)",
            self.ui.lineEdit_contact_postalCode: "CEP (Contato)",
            self.ui.lineEdit_contact_email: "E-mail (Contato)",
            self.ui.lineEdit_contact_country: "País (Contato)",
            self.ui.comboBox_contact_role: "Responsabilidade (Contato)",
            self.ui.lineEdit_MD_Keywords: "Palavras-chave",
            self.ui.comboBox_MD_SpatialRepresentationTypeCode: "Tipo de Representação Espacial",
            self.ui.comboBox_LanguageCode: "Idioma",
            self.ui.comboBox_topicCategory: "Categoria Temática",
            self.ui.comboBox_hierarchyLevel: "Nível Hierárquico"
        }

        for widget, friendly_name in required_fields.items():
            is_invalid = False
            if isinstance(widget, QtWidgets.QLineEdit) and not widget.text().strip():
                is_invalid = True
            elif isinstance(widget, QtWidgets.QTextEdit) and not widget.toPlainText().strip():
                is_invalid = True
            elif isinstance(widget, QtWidgets.QComboBox) and widget.currentIndex() == -1:
                is_invalid = True
            
            if is_invalid:
                errors.append(friendly_name)

        if not self.ui.lineEdit_westBoundLongitude.text().strip() or \
           not self.ui.lineEdit_eastBoundLongitude.text().strip() or \
           not self.ui.lineEdit_southBoundLatitude.text().strip() or \
           not self.ui.lineEdit_northBoundLatitude.text().strip():
            errors.append("Coordenadas Geográficas (Extensão)")

        if errors:
            error_message = "<p style='font-size:15px; font-weight: bold;'>Preencha os campos obrigatórios!</p><b>São os seguintes campos:</b><ul>"
            for error in errors:
                error_message += f"<li>{error}</li>"
            error_message += "</ul>"
            QtWidgets.QMessageBox.warning(self.parent, "Campos Faltando", error_message)
            return False
            
        return True

    def collect_data(self):
        data = {}
        preset_key = self.ui.comboBox_contact_presets.currentData()
        if preset_key and preset_key != 'nenhum': 
            data['uuid'] = self.contatos_predefinidos.get(preset_key, {}).get('uuid')

        raw_keywords_text = self.ui.lineEdit_MD_Keywords.text()
        normalized_text = re.sub(r'[\s;./]+', ',', raw_keywords_text)
        keywords_list = [k.strip() for k in normalized_text.split(',') if k.strip()]

        raw_scale_text = self.ui.lineEdit_textEdit_spatialResolution_denominator.text()
        cleaned_scale_text = raw_scale_text.replace('.', '').replace(',', '')
        all_numbers_in_scale = re.findall(r'\d+', cleaned_scale_text)
        scale_value = all_numbers_in_scale[-1] if all_numbers_in_scale else ""

        data.update({
            'title': self.ui.lineEdit_title.text(),
            'edition': str(self.ui.spinBox_edition.value()),
            'abstract': self.ui.textEdit_abstract.toPlainText(),
            'MD_Keywords': keywords_list,
            'spatialResolution_denominator': scale_value,
            'contact_individualName': self.ui.lineEdit_contact_individualName.text(),
            'contact_organisationName': self.ui.lineEdit_contact_organisationName.text(),
            'contact_positionName': self.ui.lineEdit_contact_positionName.text(),
            'contact_phone': self.ui.lineEdit_contact_phone.text(),
            'contact_deliveryPoint': self.ui.lineEdit_contact_deliveryPoint.text(),
            'contact_city': self.ui.lineEdit_contact_city.text(),
            'contact_postalCode': self.ui.lineEdit_contact_postalCode.text(),
            'contact_country': self.ui.lineEdit_contact_country.text(),
            'contact_email': self.ui.lineEdit_contact_email.text(),
            'dateStamp': self.ui.dateTimeEdit_dateStamp.dateTime().toUTC().toString("yyyy-MM-ddTHH:mm:ss'Z'"),
            'date_creation': self.ui.dateTimeEdit_date_creation.dateTime().toPyDateTime().astimezone().isoformat(),
            'status_codeListValue': self.ui.comboBox_status_codeListValue.currentData(),
            'MD_SpatialRepresentationTypeCode': self.ui.comboBox_MD_SpatialRepresentationTypeCode.currentData(),
            'LanguageCode': self.ui.comboBox_LanguageCode.currentData(),
            'characterSet': self.ui.comboBox_characterSet.currentData(),
            'topicCategory': self.ui.comboBox_topicCategory.currentData(),
            'hierarchyLevel': self.ui.comboBox_hierarchyLevel.currentData(),
            'contact_administrativeArea': self.ui.comboBox_contact_administrativeArea.currentData(),
            'contact_role': self.ui.comboBox_contact_role.currentData(),
            'westBoundLongitude': self.ui.lineEdit_westBoundLongitude.text(),
            'eastBoundLongitude': self.ui.lineEdit_eastBoundLongitude.text(),
            'southBoundLatitude': self.ui.lineEdit_southBoundLatitude.text(),
            'northBoundLatitude': self.ui.lineEdit_northBoundLatitude.text(),
            'contact_preset_key': self.ui.comboBox_contact_presets.currentData(),
            'thumbnail_url': self.ui.lineEdit_thumbnail_url.text(),
            'metadata_uuid': self.current_metadata_uuid
        })
        data.update(self.distribution_data)
        return data

    def populate_form_from_dict(self, data_dict):
        if not data_dict: return
        self.current_metadata_uuid = data_dict.get('metadata_uuid')
        self.ui.lineEdit_title.setText(data_dict.get('title', ''))
        try: self.ui.spinBox_edition.setValue(int(data_dict.get('edition', '1') or '1'))
        except (ValueError, TypeError): self.ui.spinBox_edition.setValue(1)
        self.ui.textEdit_abstract.setText(data_dict.get('abstract', ''))
        self.ui.lineEdit_MD_Keywords.setText(','.join(data_dict.get('MD_Keywords', [])))
        self.ui.lineEdit_textEdit_spatialResolution_denominator.setText(data_dict.get('spatialResolution_denominator', ''))
        self.ui.lineEdit_contact_individualName.setText(data_dict.get('contact_individualName', ''))
        self.ui.lineEdit_contact_organisationName.setText(data_dict.get('contact_organisationName', ''))
        self.ui.lineEdit_contact_positionName.setText(data_dict.get('contact_positionName', ''))
        self.ui.lineEdit_contact_phone.setText(data_dict.get('contact_phone', ''))
        self.ui.lineEdit_contact_deliveryPoint.setText(data_dict.get('contact_deliveryPoint', ''))
        self.ui.lineEdit_contact_city.setText(data_dict.get('contact_city', ''))
        self.ui.lineEdit_contact_postalCode.setText(data_dict.get('contact_postalCode', ''))
        self.ui.lineEdit_contact_country.setText(data_dict.get('contact_country', ''))
        self.ui.lineEdit_contact_email.setText(data_dict.get('contact_email', ''))

        for key, combo in {'status_codeListValue': self.ui.comboBox_status_codeListValue, 'MD_SpatialRepresentationTypeCode': self.ui.comboBox_MD_SpatialRepresentationTypeCode, 'LanguageCode': self.ui.comboBox_LanguageCode, 'characterSet': self.ui.comboBox_characterSet, 'topicCategory': self.ui.comboBox_topicCategory, 'hierarchyLevel': self.ui.comboBox_hierarchyLevel, 'contact_administrativeArea': self.ui.comboBox_contact_administrativeArea, 'contact_role': self.ui.comboBox_contact_role}.items():
            self.set_combobox_by_data(combo, data_dict.get(key))

        self.ui.lineEdit_westBoundLongitude.setText(data_dict.get('westBoundLongitude', ''))
        self.ui.lineEdit_eastBoundLongitude.setText(data_dict.get('eastBoundLongitude', ''))
        self.ui.lineEdit_southBoundLatitude.setText(data_dict.get('southBoundLatitude', ''))
        self.ui.lineEdit_northBoundLatitude.setText(data_dict.get('northBoundLatitude', ''))

        date_creation_str = data_dict.get('date_creation')
        if date_creation_str:
            try:
                dt = QDateTime.fromString(date_creation_str, Qt.ISODateWithMs)
                if not dt.isValid(): dt = QDateTime.fromString(date_creation_str, Qt.ISODate)
                self.ui.dateTimeEdit_date_creation.setDateTime(dt)
            except Exception as e: print(f"Erro ao converter data: {e}")

        self.distribution_data['wms_data'] = data_dict.get('wms_data', {})
        self.distribution_data['wfs_data'] = data_dict.get('wfs_data', {})
        self.ui.lineEdit_thumbnail_url.setText(data_dict.get('thumbnail_url', ''))

        found_preset_key = None
        for preset_key, preset_data in self.contatos_predefinidos.items():
            if preset_key == 'nenhum': continue
            if (data_dict.get('contact_individualName') == preset_data.get('contact_individualName') and
                data_dict.get('contact_organisationName') == preset_data.get('contact_organisationName') and
                data_dict.get('contact_email') == preset_data.get('contact_email')):
                found_preset_key = preset_key
                break

        preset_to_set = found_preset_key if found_preset_key else 'nenhum'
        self.set_combobox_by_data(self.ui.comboBox_contact_presets, preset_to_set)

    def on_contact_preset_changed(self):
        preset_key = self.ui.comboBox_contact_presets.currentData()
        contact_data = self.contatos_predefinidos.get(preset_key, {})
        self.ui.lineEdit_contact_individualName.setText(contact_data.get('contact_individualName', ''))
        self.ui.lineEdit_contact_organisationName.setText(contact_data.get('contact_organisationName', ''))
        self.ui.lineEdit_contact_positionName.setText(contact_data.get('contact_positionName', ''))
        self.ui.lineEdit_contact_phone.setText(contact_data.get('contact_phone', ''))
        self.ui.lineEdit_contact_deliveryPoint.setText(contact_data.get('contact_deliveryPoint', ''))
        self.ui.lineEdit_contact_city.setText(contact_data.get('contact_city', ''))
        self.ui.lineEdit_contact_postalCode.setText(contact_data.get('contact_postalCode', ''))
        self.ui.lineEdit_contact_country.setText(contact_data.get('contact_country', ''))
        self.ui.lineEdit_contact_email.setText(contact_data.get('contact_email', ''))
        self.set_combobox_by_data(self.ui.comboBox_contact_administrativeArea, contact_data.get('contact_administrativeArea', ''))
        self.set_combobox_by_data(self.ui.comboBox_contact_role, contact_data.get('contact_role', ''))

    def set_combobox_by_data(self, combo_box, data_value):
        index = combo_box.findData(data_value)
        if index != -1: combo_box.setCurrentIndex(index)

    def connect_dirty_signals(self, callback_func):
        """Conecta eventos de edição a uma função passada pra sujar a UI."""
        def mark_dirty():
            if not self._is_metadata_dirty:
                self._is_metadata_dirty = True
                callback_func()
                
        # Inputs de Texto Livre
        for obj in [
            self.ui.lineEdit_title, self.ui.textEdit_abstract, self.ui.lineEdit_MD_Keywords,
            self.ui.lineEdit_textEdit_spatialResolution_denominator, self.ui.lineEdit_contact_individualName,
            self.ui.lineEdit_contact_organisationName, self.ui.lineEdit_contact_positionName,
            self.ui.lineEdit_contact_phone, self.ui.lineEdit_contact_deliveryPoint,
            self.ui.lineEdit_contact_city, self.ui.lineEdit_contact_postalCode,
            self.ui.lineEdit_contact_country, self.ui.lineEdit_contact_email,
            self.ui.lineEdit_thumbnail_url
        ]:
            if obj: obj.textChanged.connect(mark_dirty)

        for obj in [self.ui.spinBox_edition]:
            if obj: obj.valueChanged.connect(mark_dirty)

        # ComboBoxes 
        for combo in [
            self.ui.comboBox_status_codeListValue, self.ui.comboBox_MD_SpatialRepresentationTypeCode,
            self.ui.comboBox_LanguageCode, self.ui.comboBox_characterSet, self.ui.comboBox_topicCategory,
            self.ui.comboBox_hierarchyLevel, self.ui.comboBox_contact_administrativeArea,
            self.ui.comboBox_contact_role, self.ui.comboBox_contact_presets
        ]:
            if combo: combo.currentIndexChanged.connect(mark_dirty)

        # Datas
        if getattr(self.ui, 'dateTimeEdit_dateStamp', None): self.ui.dateTimeEdit_dateStamp.dateTimeChanged.connect(mark_dirty)
        if getattr(self.ui, 'dateTimeEdit_date_creation', None): self.ui.dateTimeEdit_date_creation.dateTimeChanged.connect(mark_dirty)

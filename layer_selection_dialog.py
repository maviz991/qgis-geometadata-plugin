# layer_selection_dialog.py
import os
import requests
from lxml import etree as ET
from qgis.PyQt import uic, QtWidgets

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'layer_selection_dialog_base.ui'))

class LayerSelectionDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, credentials, parent=None):
        super(LayerSelectionDialog, self).__init__(parent)
        self.setupUi(self)

        if not credentials:
            raise ValueError("Credenciais são necessárias para inicializar este diálogo.")
        
        self.creds = credentials
        self.data = {}

        self.comboBox_service_type.addItem("Selecione um serviço...", None)
        self.comboBox_service_type.addItem("WMS (Imagem)", "wms")
        self.comboBox_service_type.addItem("WFS (Vetor)", "wfs")
        self.comboBox_service_type.currentIndexChanged.connect(self._fetch_layers)

    def _fetch_layers(self):
        service = self.comboBox_service_type.currentData()
        if not service:
            self.comboBox_layers.clear()
            self.comboBox_layers.setEnabled(False)
            return

        self.comboBox_layers.clear()
        self.comboBox_layers.setEnabled(False)
        self.comboBox_layers.addItem("Carregando...")

        # A URL base é a mesma, mas a requisição muda
        if service == 'wms':
            url = f"{self.creds['url']}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
        else: # wfs
            url = f"{self.creds['url']}/ows?service=WFS&version=1.0.0&request=GetCapabilities"

        try:
            response = requests.get(url, auth=(self.creds['user'], self.creds['password']), timeout=20)
            response.raise_for_status()

            self.comboBox_layers.clear()
            self.comboBox_layers.addItem("", None)
            
            root = ET.fromstring(response.content)
            layers_found = []

            if service == 'wms':
                ns = {'wms': 'http://www.opengis.net/wms'}
                # A tag Title está fora da tag Name para WMS 1.3.0
                for layer_node in root.findall('.//wms:Layer/wms:Name/..', namespaces=ns):
                    name = layer_node.find('wms:Name', ns).text
                    title = layer_node.find('wms:Title', ns).text
                    if name and title:
                        layers_found.append({'name': name, 'title': title})
            else: # wfs
                ns = {'wfs': 'http://www.opengis.net/wfs'}
                for feature_type in root.findall('.//wfs:FeatureType', namespaces=ns):
                    name = feature_type.find('wfs:Name', ns).text
                    title = feature_type.find('wfs:Title', ns).text
                    if name and title:
                        layers_found.append({'name': name, 'title': title})
            
            for layer in sorted(layers_found, key=lambda x: x['title']):
                self.comboBox_layers.addItem(f"{layer['title']} ({layer['name']})", layer)
            
            self.comboBox_layers.setEnabled(True)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erro", f"Falha ao carregar camadas: {e}")
            self.comboBox_layers.clear()
            self.comboBox_layers.addItem("Falha ao carregar", None)

    def accept(self):
        selected_layer = self.comboBox_layers.currentData()
        self.data = {
            'thumbnail_url': self.lineEdit_thumbnail_url.text(),
            'geoserver_base_url': self.creds['url'],
            'online_protocol': self.comboBox_service_type.currentData().upper() if self.comboBox_service_type.currentData() else None,
            'geoserver_layer_name': selected_layer['name'] if selected_layer else None,
            'geoserver_layer_title': selected_layer['title'] if selected_layer else None
        }
        super().accept()

    def get_data(self):
        return self.data


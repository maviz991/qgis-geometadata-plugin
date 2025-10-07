# layer_selection_dialog.py (VERSÃO FINAL COM CORREÇÃO NA FUNÇÃO ACCEPT)

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
        # Variáveis para guardar os dados antigos para o caso do usuário não selecionar nada novo
        self.previously_selected_layer_name = None
        self.previously_selected_layer_title = None

        self.comboBox_service_type.addItem("Selecione um serviço...", None)
        self.comboBox_service_type.addItem("WMS (Imagem)", "wms")
        self.comboBox_service_type.addItem("WFS (Vetor)", "wfs")
        self.comboBox_service_type.currentIndexChanged.connect(self._fetch_layers)

    def _fetch_layers(self):
        print("DEBUG: _fetch_layers called.") # DEBUG
        service = self.comboBox_service_type.currentData()
        print(f"DEBUG: _fetch_layers - service: {service}") # DEBUG
        if not service:
            self.comboBox_layers.clear()
            self.comboBox_layers.setEnabled(False)
            print("DEBUG: _fetch_layers - No service, returning.") # DEBUG
            return

        self.comboBox_layers.clear()
        self.comboBox_layers.setEnabled(False)
        self.comboBox_layers.addItem("Carregando...")

        # Check if the previously selected layer is already in the combo box
        if self.previously_selected_layer_name:
            for i in range(self.comboBox_layers.count()):
                layer_data = self.comboBox_layers.itemData(i)
                if layer_data and layer_data.get('name') == self.previously_selected_layer_name:
                    self.comboBox_layers.setCurrentIndex(i)
                    self.comboBox_layers.setEnabled(True)
                    return

        if service == 'wms':
            url = f"{self.creds['url']}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
        else: # wfs
            url = f"{self.creds['url']}/wfs"

        try:
            response = requests.get(url, auth=(self.creds['user'], self.creds['password']), timeout=20, verify=False)
            response.raise_for_status()

            self.comboBox_layers.clear()
            self.comboBox_layers.addItem("", None)
            
            root = ET.fromstring(response.content)
            layers_found = []

            if service == 'wms':
                ns = {'wms': 'http://www.opengis.net/wms'}
                for layer_node in root.findall('.//wms:Layer/wms:Name/..', namespaces=ns):
                    name = layer_node.find('wms:Name', ns).text
                    title = layer_node.find('wms:Title', ns).text
                    if name and title: layers_found.append({'name': name, 'title': title})
            else: # wfs
                ns = {'wfs': 'http://www.opengis.net/wfs'}
                for feature_type in root.findall('.//wfs:FeatureType', namespaces=ns):
                    name = feature_type.find('wfs:Name', ns).text
                    title = feature_type.find('wfs:Title', ns).text
                    if name and title: layers_found.append({'name': name, 'title': title})
            
            for layer in sorted(layers_found, key=lambda x: x['title']):
                self.comboBox_layers.addItem(f"{layer['title']} ({layer['name']})", layer)
            
            if self.previously_selected_layer_name:
                for i in range(self.comboBox_layers.count()):
                    layer_data = self.comboBox_layers.itemData(i)
                    if layer_data and layer_data.get('name') == self.previously_selected_layer_name:
                        self.comboBox_layers.setCurrentIndex(i)
                        break

            self.comboBox_layers.setEnabled(True)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erro", f"Falha ao carregar camadas: {e}")
            self.comboBox_layers.clear()
            self.comboBox_layers.addItem("Falha ao carregar", None)

    def set_data(self, data):
        """Pré-preenche os campos e guarda os dados antigos para referência."""
        if not data:
            print("DEBUG: set_data received empty data.") # DEBUG
            return
        
        print(f"DEBUG: set_data received data: {data}") # DEBUG
        self.previously_selected_layer_name = data.get('geoserver_layer_name')
        self.previously_selected_layer_title = data.get('geoserver_layer_title')
        self.previously_selected_online_protocol = data.get('online_protocol')
        
        print(f"DEBUG: previously_selected_online_protocol: {self.previously_selected_online_protocol}") # DEBUG

        # Set the comboBox_service_type to the previously selected value, if available
        if self.previously_selected_online_protocol:
            service_protocol = self.previously_selected_online_protocol
            service_key = service_protocol.split(':')[-1].lower()
            index = self.comboBox_service_type.findData(service_key)
            print(f"DEBUG: service_key: {service_key}, index: {index}") # DEBUG
            if index >= 0:
                self.comboBox_service_type.setCurrentIndex(index)
                print(f"DEBUG: comboBox_service_type set to index {index} for service_key {service_key}") # DEBUG

    def accept(self):
        """Lógica de aceitação NÃO-DESTRUTIVA."""
        selected_layer = self.comboBox_layers.currentData()
        
        self.data = {
            'geoserver_base_url': self.creds['url'],
            'online_protocol': self.comboBox_service_type.currentData().upper() if self.comboBox_service_type.currentData() else None
        }
        
        if selected_layer:
            # O usuário fez uma nova seleção, então usamos os novos dados
            self.data['geoserver_layer_name'] = selected_layer.get('name')
            self.data['geoserver_layer_title'] = selected_layer.get('title')
            self.data['online_protocol'] = self.comboBox_service_type.currentData().upper() if self.comboBox_service_type.currentData() else None
        else:
            # O usuário NÃO fez uma nova seleção, então PRESERVAMOS os dados antigos
            self.data['geoserver_layer_name'] = self.previously_selected_layer_name
            self.data['geoserver_layer_title'] = self.previously_selected_layer_title
            self.data['online_protocol'] = self.previously_selected_online_protocol

        super().accept()

    def get_data(self):
        return self.data
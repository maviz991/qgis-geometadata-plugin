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
        self.wms_data = None
        self.wfs_data = None

        # Variáveis para guardar os dados antigos para o caso do usuário não selecionar nada novo
        self.previously_selected_layer_name = None
        self.previously_selected_layer_title = None
        self.previously_selected_online_protocol = None # Adicionado para consistência        

        self.comboBox_service_type.addItem("Selecione um serviço...", None)
        self.comboBox_service_type.addItem("WMS (Imagem)", "wms")
        self.comboBox_service_type.addItem("WFS (Vetor)", "wfs")
        self.comboBox_service_type.currentIndexChanged.connect(self._fetch_layers)

        self.btn_addservice.clicked.connect(self._add_service_selection)
        self.btn_wms.clicked.connect(lambda: self._clear_service_selection("wms"))
        self.btn_wfs.clicked.connect(lambda: self._clear_service_selection("wfs"))    

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
                    print(f"DEBUG: _fetch_layers - Previously selected layer found at index: {i}")
                    return

        if service == 'wms':
            url = f"{self.creds['url']}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
        else: # wfs
            url = f"{self.creds['url']}/ows?service=WFS&version=1.1.0&request=GetCapabilities"

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
                for i in range(1, self.comboBox_layers.count()):  # Start from index 1 to skip the empty item
                    layer_data = self.comboBox_layers.itemData(i)
                    if layer_data and layer_data.get('name') == self.previously_selected_layer_name:
                        self.comboBox_layers.setCurrentIndex(i)
                        print(f"DEBUG: _fetch_layers - Previously selected layer found and reselected at index: {i}")
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

        # Update internal wms_data and wfs_data
        self.wms_data = data.get('wms_data')
        self.wfs_data = data.get('wfs_data')

        # Update WMS button
        if self.wms_data:
            self.btn_wms.setText(f"WMS: {self.wms_data.get('geoserver_layer_title')}")
            self.btn_wms.setEnabled(True)
        else:
            self.btn_wms.setText("WMS Não Adicionado")
            self.btn_wms.setEnabled(False)

        # Update WFS button
        if self.wfs_data:
            self.btn_wfs.setText(f"WFS: {self.wfs_data.get('geoserver_layer_title')}")
            self.btn_wfs.setEnabled(True)
        else:
            self.btn_wfs.setText("WFS Não Adicionado")
            self.btn_wfs.setEnabled(False)

        # Reset comboboxes for new selection
        # Select the service type based on the online_protocol
        if data and data.get('wms_data') and data.get('wms_data').get('online_protocol') == 'WMS':
            self.comboBox_service_type.setCurrentIndex(1)  # WMS
        elif data and data.get('wfs_data') and data.get('wfs_data').get('online_protocol') == 'WFS':
            self.comboBox_service_type.setCurrentIndex(2)  # WFS
        else:
            self.comboBox_service_type.setCurrentIndex(0)  # Select "Selecione um serviço..."
        
        self.comboBox_layers.clear()
        self.comboBox_layers.setEnabled(False)
        print(f"DEBUG: set_data - comboBox_service_type current index: {self.comboBox_service_type.currentIndex()}")
        print(f"DEBUG: set_data - comboBox_layers current index: {self.comboBox_layers.currentIndex()}")
        print(f"DEBUG: set_data - self.wms_data: {self.wms_data}")
        print(f"DEBUG: set_data - self.wfs_data: {self.wfs_data}")

    def _add_service_selection(self):
        """Adiciona o serviço e camada selecionados aos dados de WMS ou WFS."""
        service_type = self.comboBox_service_type.currentData()
        selected_layer = self.comboBox_layers.currentData()

        if not service_type or not selected_layer:
            QtWidgets.QMessageBox.warning(self, "Aviso", "Selecione um tipo de serviço e uma camada.")
            return

        service_data = {
            'geoserver_base_url': self.creds['url'],
            'geoserver_layer_name': selected_layer.get('name'),
            'geoserver_layer_title': selected_layer.get('title'),
            'online_protocol': service_type.upper()
        }

        if service_type == "wms":
            self.wms_data = service_data
            self.btn_wms.setText(f"WMS: {selected_layer.get('title')}")
            self.btn_wms.setEnabled(True)
        elif service_type == "wfs":
            self.wfs_data = service_data
            self.btn_wfs.setText(f"WFS: {selected_layer.get('title')}")
            self.btn_wfs.setEnabled(True)
        
        QtWidgets.QMessageBox.information(self, "Serviço Adicionado", f"Serviço {service_type.upper()} adicionado com sucesso!")
        self.comboBox_service_type.setCurrentIndex(0) # Reset combo box
        self.comboBox_layers.clear()
        self.comboBox_layers.setEnabled(False)
        self.previously_selected_layer_name = selected_layer.get('name')
        self.previously_selected_layer_title = selected_layer.get('title')
        self.previously_selected_online_protocol = service_type.upper()

    def _clear_service_selection(self, service_type):
        """Limpa a seleção de um serviço específico (WMS ou WFS)."""
        if service_type == "wms":
            self.wms_data = None
            self.btn_wms.setText("WMS Não Adicionado")
            self.btn_wms.setEnabled(False)
        elif service_type == "wfs":
            self.wfs_data = None
            self.btn_wfs.setText("WFS Não Adicionado")
            self.btn_wfs.setEnabled(False)
        QtWidgets.QMessageBox.information(self, "Serviço Removido", f"Serviço {service_type.upper()} removido.")

    def accept(self):
        """Lógica de aceitação para coletar dados de WMS e WFS."""
        data = {
            'geoserver_base_url': self.creds['url'],
            'wms_data': self.wms_data,
            'wfs_data': self.wfs_data
        }
        # Store the data in self.data
        self.data = data
        print(f"DEBUG: accept - self.wms_data: {self.wms_data}")
        print(f"DEBUG: accept - self.wfs_data: {self.wfs_data}")
        super().accept()

    def get_data(self):
        return self.data
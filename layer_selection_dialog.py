# layer_selection_dialog.py (VERSÃO REFATORADA PARA USAR api_session)

import os
import requests
from lxml import etree as ET
from qgis.PyQt import uic, QtWidgets
from .plugin_config import config_loader
from qgis.PyQt.QtGui import QIcon


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'layer_selection_dialog_base.ui'))

class LayerSelectionDialog(QtWidgets.QDialog, FORM_CLASS):
    # --- MUDANÇA 1: O construtor agora recebe a SESSÃO DE API ---
    def __init__(self, api_session, parent=None):
        super(LayerSelectionDialog, self).__init__(parent)
        self.setupUi(self)

        if not api_session:
            raise ValueError("Uma sessão de API autenticada é necessária para inicializar este diálogo.")
        
        # Armazena a sessão e obtém a URL do GeoServer a partir da configuração
        self.api_session = api_session
        self.geoserver_url = config_loader.get_geoserver_url()
        
        self.data = {}
        self.wms_data = None
        self.wfs_data = None

        self.icon_wms = QIcon(":/plugins/geometadata/img/wms_icon.png")
        self.icon_wfs = QIcon(":/plugins/geometadata/img/wfs_icon.png")

        self.comboBox_service_type.addItem("Selecione um serviço...", None)           
        self.comboBox_service_type.addItem(self.icon_wms, "WMS (Imagem)", "wms")
        self.comboBox_service_type.addItem(self.icon_wfs, "WFS (Vetor)", "wfs")
        self.comboBox_service_type.currentIndexChanged.connect(self._fetch_layers)

        self.btn_addservice.clicked.connect(self._add_service_selection)
        self.btn_wms.clicked.connect(lambda: self._clear_service_selection("wms"))
        self.btn_wfs.clicked.connect(lambda: self._clear_service_selection("wfs"))



    def _fetch_layers(self):
        service = self.comboBox_service_type.currentData()
        if not service:
            self.comboBox_layers.clear()
            self.comboBox_layers.setEnabled(False)
            return

        self.comboBox_layers.clear()
        self.comboBox_layers.setEnabled(False)
        self.comboBox_layers.addItem("Carregando...")

        # Constrói a URL do GetCapabilities
        if service == 'wms':
            url = f"{self.geoserver_url}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
        else: # wfs
            url = f"{self.geoserver_url}/ows?service=WFS&version=1.1.0&request=GetCapabilities"

        try:
            # --- MUDANÇA 2: USA A SESSÃO AUTENTICADA PARA A REQUISIÇÃO ---
            # O parâmetro 'auth' não é mais necessário, pois a sessão já tem o cookie.
            response = self.api_session.get(url, timeout=20, verify=False)
            response.raise_for_status()

            self.comboBox_layers.clear()
            self.comboBox_layers.addItem("Selecione uma camada...", None)
            
            root = ET.fromstring(response.content)
            layers_found = []

            # A lógica de parse do XML permanece a mesma
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
            
            self.comboBox_layers.setEnabled(True)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Falha ao carregar camadas do GeoServer: {e}")
            self.comboBox_layers.clear()
            self.comboBox_layers.addItem("Falha ao carregar", None)

    def set_data(self, data):
        """Pré-preenche os botões com os dados de WMS/WFS já salvos."""
        if not data: return
        
        self.wms_data = data.get('wms_data')
        self.wfs_data = data.get('wfs_data')

        if self.wms_data:
            self.btn_wms.setIcon(self.icon_wms)
            self.btn_wms.setText(f"WMS: {self.wms_data.get('geoserver_layer_title')}")
            self.btn_wms.setEnabled(True)
        else:
            self.btn_wms.setText("WMS Não Adicionado")
            self.btn_wms.setEnabled(False)

        if self.wfs_data:
            self.btn_wfs.setIcon(self.icon_wfs)
            self.btn_wfs.setText(f"WFS: {self.wfs_data.get('geoserver_layer_title')}")
            self.btn_wfs.setEnabled(True)
        else:
            self.btn_wfs.setText("WFS Não Adicionado")
            self.btn_wfs.setEnabled(False)

    def _add_service_selection(self):
        """Adiciona o serviço e camada selecionados aos dados de WMS ou WFS."""
        service_type = self.comboBox_service_type.currentData()
        selected_layer = self.comboBox_layers.currentData()

        if not service_type or not selected_layer:
            QtWidgets.QMessageBox.warning(self, "Aviso", "Selecione um tipo de serviço e uma camada.")
            return

        service_data = {
            # --- MUDANÇA 3: Usa a URL da configuração ---
            'geoserver_base_url': self.geoserver_url,
            'geoserver_layer_name': selected_layer.get('name'),
            'geoserver_layer_title': selected_layer.get('title'),
            'online_protocol': service_type.upper()
        }

        if service_type == "wms":
            self.wms_data = service_data
            self.btn_wms.setIcon(self.icon_wms)
            self.btn_wms.setText(f"WMS: {selected_layer.get('title')}")
            self.btn_wms.setEnabled(True)
        elif service_type == "wfs":
            self.wfs_data = service_data
            self.btn_wfs.setIcon(self.icon_wfs)            
            self.btn_wfs.setText(f"WFS: {selected_layer.get('title')}")
            self.btn_wfs.setEnabled(True)
        
        # Resetar a UI para a próxima seleção
        self.comboBox_service_type.setCurrentIndex(0)
        self.comboBox_layers.clear()
        self.comboBox_layers.setEnabled(False)

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
        """Coleta os dados finais de WMS e WFS antes de fechar."""
        self.data = {
            # --- MUDANÇA 4: Usa a URL da configuração ---
            'geoserver_base_url': self.geoserver_url,
            'wms_data': self.wms_data,
            'wfs_data': self.wfs_data
        }
        super().accept()

    def get_data(self):
        return self.data
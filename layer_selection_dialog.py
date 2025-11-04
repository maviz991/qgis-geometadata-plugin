# layer_selection_dialog.py (VERSÃO REFATORADA PARA USAR api_session)

import os
import requests
from lxml import etree as ET
from qgis.PyQt import uic, QtWidgets
from .plugin_config import config_loader
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt, QStringListModel


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'layer_selection_dialog_base.ui'))

# layer_selection_dialog.py
class LayerSelectionDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, api_session, parent=None):
        super(LayerSelectionDialog, self).__init__(parent)
        self.setupUi(self)

        if not api_session:
            raise ValueError("Uma sessão de API autenticada é necessária.")
        
        self.api_session = api_session
        self.geoserver_url = config_loader.get_geoserver_url()
        
        self.all_layers = []
        self.layer_data_map = {} # Mapeia o texto de exibição para os dados da camada
        self.selected_layer_data = None
        
        self.data = {}
        self.wms_data = None
        self.wfs_data = None

        # --- CONFIGURAÇÃO DO QCOMPLETER ---
        self.completer = QtWidgets.QCompleter(self)
        self.completer_model = QStringListModel(self)
        self.completer.setModel(self.completer_model)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.lineEdit_layer_search.setCompleter(self.completer)

        # --- Ícones e ComboBox de Serviço ---
        self.icon_wms = QIcon(":/plugins/geometadata/img/wms_icon.png")
        self.icon_wfs = QIcon(":/plugins/geometadata/img/wfs_icon.png")
        self.comboBox_service_type.addItem("Selecione um serviço...", None)           
        self.comboBox_service_type.addItem(self.icon_wms, "WMS (Imagem)", "wms")
        self.comboBox_service_type.addItem(self.icon_wfs, "WFS (Vetor)", "wfs")
        
        # --- Conexões de Sinais ---
        self.comboBox_service_type.currentIndexChanged.connect(self._fetch_layers)
        self.completer.activated.connect(self._on_layer_selected)
        self.btn_addservice.clicked.connect(self._add_service_selection)
        self.btn_wms.clicked.connect(lambda: self._clear_service_selection("wms"))
        self.btn_wfs.clicked.connect(lambda: self._clear_service_selection("wfs"))
        
        self.lineEdit_layer_search.setEnabled(False)

    def _fetch_layers(self):
        service = self.comboBox_service_type.currentData()
        # Limpa tudo ao mudar de serviço
        self.all_layers.clear()
        self.layer_data_map.clear()
        self.completer_model.setStringList([])
        self.lineEdit_layer_search.clear()
        self.selected_layer_data = None

        if not service:
            self.lineEdit_layer_search.setEnabled(False)
            return

        self.lineEdit_layer_search.setText("Carregando...")
        self.lineEdit_layer_search.setEnabled(False)
        

        if service == 'wms':
            url = f"{self.geoserver_url}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
        else: # wfs
            url = f"{self.geoserver_url}/ows?service=WFS&version=1.1.0&request=GetCapabilities"

        try:
            response = self.api_session.get(url, timeout=20, verify=False)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            layers_found = []
            
            # Sua lógica de parse do XML (que está perfeita)
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

            self.all_layers = sorted(layers_found, key=lambda x: x['title'])
            
            display_list = []
            for layer in self.all_layers:
                display_text = f"{layer.get('title')} ({layer.get('name')})"
                display_list.append(display_text)
                self.layer_data_map[display_text] = layer

            self.completer_model.setStringList(display_list)
            
            self.lineEdit_layer_search.setEnabled(True)
            self.lineEdit_layer_search.clear()
            self.lineEdit_layer_search.setFocus()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Falha ao carregar camadas do GeoServer: {e}")
            self.lineEdit_layer_search.lineEdit().setText("Falha ao carregar")

    # Substitua seu método _filter_layer_list por este:
    def _filter_layer_list(self, filter_text, show_popup=True):
        """
        Filtra, repopula o QComboBox e exibe o popup, preservando o texto e foco do usuário.
        """
        line_edit = self.lineEdit_layer_search.lineEdit()
        text_before_filter = line_edit.text()
        cursor_pos = line_edit.cursorPosition()

        # Bloqueia sinais para evitar loops de eventos
        self.lineEdit_layer_search.blockSignals(True)

        self.lineEdit_layer_search.clear()
        
        # Adiciona apenas os itens que correspondem ao filtro
        for layer in self.all_layers:
            title = layer.get('title', '').lower()
            name = layer.get('name', '').lower()
            
            if filter_text.lower() in title or filter_text.lower() in name:
                display_text = f"{layer.get('title')} ({layer.get('name')})"
                self.lineEdit_layer_search.addItem(display_text, layer)

        # Restaura o texto e a posição do cursor, mantendo a experiência de digitação
        line_edit.setText(text_before_filter)
        line_edit.setCursorPosition(cursor_pos)

        # Desbloqueia os sinais
        self.lineEdit_layer_search.blockSignals(False)

        # Mostra o popup apenas se for uma ação do usuário e houver itens para mostrar
        if show_popup and self.lineEdit_layer_search.count() > 0:
            self.lineEdit_layer_search.showPopup()

    def _on_layer_selected(self, selected_text):
        """
        Chamado quando uma camada é selecionada na lista do QCompleter.
        """
        # Usa o mapa para encontrar os dados completos da camada
        if selected_text in self.layer_data_map:
            self.selected_layer_data = self.layer_data_map[selected_text]
            print(f"Camada selecionada: {self.selected_layer_data}")
        else:
            self.selected_layer_data = None            

    def set_data(self, data):
        """Pré-preenche os botões com os dados de WMS/WFS já salvos."""
        if not data: return
        
        self.wms_data = data.get('wms_data')
        self.wfs_data = data.get('wfs_data')

        if self.wms_data:
            self.btn_wms.setIcon(self.icon_wms)
            self.btn_wms.setText(f"WMS: {self.wms_data.get('geoserver_layer_name')}")
            self.btn_wms.setEnabled(True)
        else:
            self.btn_wms.setText("WMS Não Adicionado")
            self.btn_wms.setEnabled(False)

        if self.wfs_data:
            self.btn_wfs.setIcon(self.icon_wfs)
            self.btn_wfs.setText(f"WFS: {self.wfs_data.get('geoserver_layer_name')}")
            self.btn_wfs.setEnabled(True)
        else:
            self.btn_wfs.setText("WFS Não Adicionado")
            self.btn_wfs.setEnabled(False)

    def _add_service_selection(self):
        """Adiciona o serviço e camada selecionados aos dados de WMS ou WFS."""
        service_type = self.comboBox_service_type.currentData()
        selected_layer = self.selected_layer_data 

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
            self.btn_wms.setText(f"WMS: {selected_layer.get('name')}")
            self.btn_wms.setEnabled(True)
        elif service_type == "wfs":
            self.wfs_data = service_data
            self.btn_wfs.setIcon(self.icon_wfs)            
            self.btn_wfs.setText(f"WFS: {selected_layer.get('name')}")
            self.btn_wfs.setEnabled(True)
        
        # Resetar a UI para a próxima seleção
        self.comboBox_service_type.setCurrentIndex(0)
        self.lineEdit_layer_search.clear()
        self.lineEdit_layer_search.setEnabled(False)

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
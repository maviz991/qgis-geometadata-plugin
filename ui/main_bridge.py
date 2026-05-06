# -*- coding: utf-8 -*-
"""
main_bridge.py — GeoMetadata Plugin
=====================================
Ponte de comunicação para a interface principal em HTML.
Exposto ao JS via QWebChannel como 'bridge'.
"""

import os
from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot

class MainBridge(QObject):
    """
    Ponte principal para o diálogo do plugin.
    Sinais JS -> Python e Python -> JS.
    """

    # Sinais emitidos para o JS
    nav_changed   = pyqtSignal(str)     # Notifica mudança de painel
    auth_status   = pyqtSignal(bool, str) # (is_logged, username)
    form_data_req = pyqtSignal('QVariant') # Envia dados para preencher o form

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._form_manager = getattr(dialog, 'form_manager', None)
        
    # --- Slots JS -> Python ---

    @pyqtSlot(str)
    def navigate(self, panel_id: str):
        """Muda o painel atual (home, editor, geoserver)."""
        print(f"GeoMetadata: Navegando para {panel_id}")
        self.nav_changed.emit(panel_id)

    @pyqtSlot('QVariant')
    def update_form_state(self, data):
        """
        Recebe dados do formulário HTML e atualiza o estado interno.
        Isso substitui o binding direto dos widgets PyQt.
        """
        if self._form_manager:
            # Aqui sincronizaremos os valores com o FormManager
            # por enquanto apenas logamos
            print(f"GeoMetadata: Atualizando estado do form com {len(data)} campos")
            # self._form_manager.update_from_dict(data)

    @pyqtSlot()
    def save_metadata(self):
        """Aciona o salvamento do metadado no GeoNetwork ou XML."""
        print("GeoMetadata: Acionando salvamento via Bridge")
        if hasattr(self._dialog, 'action_salvar'):
            self._dialog.action_salvar()

    @pyqtSlot()
    def start_login(self):
        """Dispara o processo de autenticação no diálogo."""
        self._dialog.authenticate()

    @pyqtSlot()
    def export_xml(self):
        """Exporta metadados para XML local."""
        self._dialog.exportar_to_xml()

    @pyqtSlot()
    def export_geohab(self):
        """Exporta metadados para o GeoNetwork (Geohab)."""
        self._dialog.exportar_to_geo()

    @pyqtSlot()
    def close_dialog(self):
        """Fecha o diálogo do plugin."""
        self._dialog.close()

    @pyqtSlot(result='QVariant')
    def get_initial_data(self):
        """Retorna dados iniciais para o painel Home e Editor."""
        is_logged = self._dialog.plugin.api_session is not None
        username = self._dialog.plugin.auth_username or "Visitante"
        return {
            "version": "3.0.0-beta",
            "user": username,
            "is_logged": is_logged
        }

    @pyqtSlot(str, result=str)
    def load_panel_html(self, panel_id: str) -> str:
        """Lê o HTML de um painel do disco e retorna como string para o JS."""
        panels_dir = os.path.join(os.path.dirname(__file__), "templates", "panels")
        panel_path = os.path.join(panels_dir, f"{panel_id}.html")
        try:
            with open(panel_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return f'<div style="padding:20px;color:red">Painel "{panel_id}" não encontrado.</div>'

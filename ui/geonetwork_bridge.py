# -*- coding: utf-8 -*-
"""
geonetwork_bridge.py — GeoMetadata Plugin
=====================================
Ponte de comunicação específica do fluxo GeoNetwork (editor de metadados):
contatos, rascunho do formulário, exportar/publicar, busca e pull no GN.
Exposto ao JS via QWebChannel como 'gnBridge'.
"""

import os
from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot
from ..core.plugin_config import config_loader


class GeoNetworkBridge(QObject):
    """
    Ponte GeoNetwork para o diálogo do plugin.
    Sinais JS -> Python e Python -> JS específicos do editor de metadados.
    """

    gn_contacts_ready        = pyqtSignal(str, str, 'QVariant')  # key, query, results
    gn_contact_enriched      = pyqtSignal(str, int, 'QVariant')  # key, idx, enriched_data
    gn_metadata_search_ready = pyqtSignal('QVariant')            # [{uuid, title, dateStamp}]
    gn_publish_succeeded     = pyqtSignal(str)  # uuid — publicação confirmada, badge -> Sincronizado
    local_save_succeeded     = pyqtSignal(str)  # uuid — save local (DB/sidecar) confirmado, recheca badge

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._gn_workers       = {}
        self._enrich_workers   = []
        self._gn_search_worker = None

    # ── Ações do menu Arquivo (exportar/publicar/salvar) ────────────────────────

    @pyqtSlot('QVariant')
    def save_metadata(self, form_data):
        """Salva o metadado (rascunho local). Recebe o dict do formulário HTML."""
        self._dialog.save_metadata(metadata_dict=form_data if isinstance(form_data, dict) else None)

    @pyqtSlot('QVariant')
    def export_xml(self, form_data):
        """Exporta metadados para XML local. Recebe o dict do formulário HTML."""
        self._dialog.exportar_to_xml(metadata_dict=form_data if isinstance(form_data, dict) else None)

    @pyqtSlot('QVariant')
    def export_geohab(self, form_data):
        """Publica o metadado no GeoNetwork. Recebe o dict do formulário HTML."""
        self._dialog.exportar_to_geo(metadata_dict=form_data if isinstance(form_data, dict) else None)

    # ── Contatos do usuário (persistidos localmente) ──────────────────────────

    def _user_contacts_path(self) -> str:
        try:
            from qgis.core import QgsApplication
            base = QgsApplication.qgisSettingsDirPath()
        except Exception:
            base = os.path.expanduser('~')
        return os.path.join(base, 'geometadata_user_contacts.json')

    def _load_user_contacts(self) -> list:
        import json
        path = self._user_contacts_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_user_contacts(self, contacts: list):
        import json
        with open(self._user_contacts_path(), 'w', encoding='utf-8') as f:
            json.dump(contacts, f, ensure_ascii=False, indent=2)

    @pyqtSlot(str)
    def save_user_contact(self, contact_json: str):
        """Salva um contato manual no arquivo local do usuário."""
        import json
        try:
            contact = json.loads(contact_json)
            if not contact.get('_key'):
                import uuid
                contact['_key'] = str(uuid.uuid4())
            contacts = self._load_user_contacts()
            for i, c in enumerate(contacts):
                if c.get('_key') == contact['_key']:
                    contacts[i] = contact
                    break
            else:
                contacts.append(contact)
            self._save_user_contacts(contacts)
            print(f"GeoMetadata: contato '{contact.get('sigla','')}' salvo localmente.")
        except Exception as e:
            print(f"GeoMetadata [save_user_contact]: {e}")

    @pyqtSlot(str)
    def delete_user_contact(self, key: str):
        """Remove um contato salvo localmente pelo seu _key."""
        try:
            contacts = self._load_user_contacts()
            contacts = [c for c in contacts if c.get('_key') != key]
            self._save_user_contacts(contacts)
            print(f"GeoMetadata: contato '{key}' removido.")
        except Exception as e:
            print(f"GeoMetadata [delete_user_contact]: {e}")

    @pyqtSlot(str, result='QVariant')
    def search_contacts(self, query: str):
        """Busca contatos nos predefinidos locais e nos contatos salvos pelo usuário."""
        predefinidos = getattr(self._dialog, 'contatos_predefinidos', {})
        q = query.lower().strip()
        results = []
        for key, data in predefinidos.items():
            if key == 'nenhum':
                continue
            org   = data.get('contact_organisationName', '')
            sigla = data.get('contact_individualName', '')
            email = data.get('contact_email', '')
            if not q or q in org.lower() or q in sigla.lower() or q in email.lower():
                results.append({
                    'sigla':    sigla,
                    'org':      org,
                    'email':    email,
                    'position': data.get('contact_positionName', ''),
                    'phone':    data.get('contact_phone', ''),
                    'address':  data.get('contact_deliveryPoint', ''),
                    'city':     data.get('contact_city', ''),
                    'state':    data.get('contact_administrativeArea', ''),
                    'zip':      data.get('contact_postalCode', ''),
                    'country':  data.get('contact_country', 'Brasil'),
                    'role':     data.get('contact_role', '')
                })
        # Contatos salvos pelo usuário
        for c in self._load_user_contacts():
            sigla = c.get('sigla', '')
            org   = c.get('org', '')
            email = c.get('email', '')
            if not q or q in org.lower() or q in sigla.lower() or q in email.lower():
                entry = dict(c)
                entry['_source'] = 'user'
                results.append(entry)
        return results

    @pyqtSlot(str, str)
    def search_contacts_gn(self, key: str, query: str):
        """Busca contatos no GeoNetwork em background (se logado). Emite gn_contacts_ready."""
        session = getattr(getattr(self._dialog, 'plugin', None), 'api_session', None)
        if not session:
            return
        from ..core.plugin_config import config_loader
        from .geonetwork_workers import _GnContactsWorker
        gn_base = config_loader.get_geonetwork_base_url()
        if not gn_base:
            return
        old = self._gn_workers.get(key)
        if old and old.isRunning():
            old.quit()
        worker = _GnContactsWorker(session, key, query, gn_base)
        worker.done.connect(lambda k, q, r: self.gn_contacts_ready.emit(k, q, r))
        self._gn_workers[key] = worker
        worker.start()

    @pyqtSlot(str, int, str)
    def enrich_gn_contact(self, section_key: str, idx: int, uuid: str):
        """Busca o XML do sub-template GeoNetwork e emite gn_contact_enriched com os campos completos."""
        session = getattr(getattr(self._dialog, 'plugin', None), 'api_session', None)
        if not session or not uuid:
            return
        from ..core.plugin_config import config_loader
        from .geonetwork_workers import _GnContactEnrichWorker
        records_url = config_loader.get_geonetwork_url().get('records_url', '')
        if not records_url:
            return
        worker = _GnContactEnrichWorker(session, uuid, records_url, section_key, idx)
        worker.done.connect(lambda k, i, d: self.gn_contact_enriched.emit(k, i, d))
        self._enrich_workers.append(worker)
        worker.start()

    @pyqtSlot(str, str)
    def export_contact_xml(self, xml_string: str, filename: str):
        """Salva o XML de sub-template de contato (ISO 19139) em arquivo escolhido pelo usuário."""
        from qgis.PyQt.QtWidgets import QFileDialog
        save_path, _ = QFileDialog.getSaveFileName(
            self._dialog,
            "Salvar contato XML",
            os.path.join(os.path.expanduser("~"), filename),
            "XML (*.xml)"
        )
        if not save_path:
            return
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(xml_string)
            print(f"GeoMetadata: contato exportado → {save_path}")
        except Exception as e:
            print(f"GeoMetadata [export_contact_xml]: {e}")

    # ── Rascunho do formulário (draft) ───────────────────────────────────────────

    def _draft_path(self) -> str:
        try:
            from qgis.core import QgsApplication
            base = QgsApplication.qgisSettingsDirPath()
        except Exception:
            base = os.path.expanduser('~')
        return os.path.join(base, 'geometadata_form_draft.json')

    def _layer_key(self) -> str:
        """Identificador estável da camada ativa (source path ou id)."""
        try:
            plugin = getattr(self._dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
            layer  = iface.activeLayer() if iface else None
            if not layer:
                return '__no_layer__'
            return layer.source() or layer.id()
        except Exception:
            return '__no_layer__'

    def _load_all_drafts(self) -> dict:
        """Lê o arquivo de drafts inteiro: {layer_key: form_data}. Migra o formato antigo
        (um único draft com '__layer_key__' na raiz) transparentemente na primeira leitura."""
        import json
        path = self._draft_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            if '__layer_key__' in raw:  # formato antigo: um draft só, sem escopo por camada
                key = raw.pop('__layer_key__')
                return {key: raw} if key else {}
            return raw
        except Exception as e:
            print(f"GeoMetadata [_load_all_drafts]: {e}")
            return {}

    def _save_all_drafts(self, drafts: dict):
        import json
        with open(self._draft_path(), 'w', encoding='utf-8') as f:
            json.dump(drafts, f, ensure_ascii=False)

    @pyqtSlot(str)
    def save_draft(self, json_str: str):
        """Persiste o rascunho do formulário sob a chave da camada ativa. Drafts de outras
        camadas (já salvos antes) não são afetados — cada camada tem seu próprio slot."""
        import json
        try:
            data = json.loads(json_str)
            drafts = self._load_all_drafts()
            drafts[self._layer_key()] = data
            self._save_all_drafts(drafts)
        except Exception as e:
            print(f"GeoMetadata [save_draft]: {e}")

    @pyqtSlot(result='QVariant')
    def load_draft(self):
        """Retorna o rascunho da camada ativa, se existir."""
        return self._load_all_drafts().get(self._layer_key())

    @pyqtSlot(result='QVariant')
    def load_layer_metadata(self):
        """Carrega metadado salvo (DB ou sidecar) da camada ativa e retorna como dict."""
        try:
            plugin = getattr(self._dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
            layer  = iface.activeLayer() if iface else None
            if not layer:
                return None
            ps = getattr(self._dialog, 'persistence_service', None)
            if not ps:
                return None
            xml_content = ps.load(layer)
            if not xml_content:
                return None
            from ..core import xml_parser
            return xml_parser.parse_xml_to_dict(xml_content, is_string=True)
        except Exception as e:
            print(f"GeoMetadata [load_layer_metadata]: {e}")
            return None

    @pyqtSlot(result='QVariant')
    def import_xml_file(self):
        """Abre um XML MGB 2.0 escolhido pelo usuário e retorna como dict pra popular o form."""
        from qgis.PyQt.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self._dialog, "Abrir Metadado XML", "", "XML (*.xml)")
        if not path:
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                xml_content = f.read()
            from ..core import xml_parser
            return xml_parser.parse_xml_to_dict(xml_content, is_string=True)
        except Exception as e:
            print(f"GeoMetadata [import_xml_file]: {e}")
            return None

    @pyqtSlot()
    def clear_draft(self):
        """Remove só o rascunho da camada ativa — não mexe nos drafts de outras camadas."""
        try:
            drafts = self._load_all_drafts()
            if drafts.pop(self._layer_key(), None) is not None:
                self._save_all_drafts(drafts)
        except Exception as e:
            print(f"GeoMetadata [clear_draft]: {e}")

    # ── Puxar do GeoNetwork (busca manual + checagem de sincronização) ─────────

    @pyqtSlot(str)
    def search_gn_metadata(self, query: str):
        """Busca registros de metadado (não subtemplates) no GN por título. Emite gn_metadata_search_ready.
        Funciona sem login (sessão anônima) — GN já filtra pra mostrar só os registros
        públicos nesse caso; os do setor exigem sessão autenticada."""
        session = getattr(getattr(self._dialog, 'plugin', None), 'api_session', None)
        if not session:
            import requests
            session = requests.Session()
        gn_base = config_loader.get_geonetwork_base_url()
        if not gn_base:
            self.gn_metadata_search_ready.emit([])
            return
        from .geonetwork_workers import _GnRecordSearchWorker
        if self._gn_search_worker and self._gn_search_worker.isRunning():
            self._gn_search_worker.quit()
        worker = _GnRecordSearchWorker(session, query, gn_base)
        worker.done.connect(lambda results: self.gn_metadata_search_ready.emit(results))
        self._gn_search_worker = worker
        worker.start()

    @pyqtSlot(str, result='QVariant')
    def pull_from_gn(self, uuid: str):
        """Busca o XML completo de um registro do GN por uuid e retorna como dict."""
        try:
            geonetwork_service = getattr(self._dialog, 'geonetwork_service', None)
            if not geonetwork_service:
                return None
            return geonetwork_service.fetch_from_geonetwork(uuid, config_loader)
        except Exception as e:
            print(f"GeoMetadata [pull_from_gn]: {e}")
            return None

    @pyqtSlot(str, str, result=str)
    def check_gn_sync(self, uuid: str, local_date_stamp: str) -> str:
        """Compara o dateStamp local com o do GN. Retorna 'synced', 'update_available',
        'not_found', 'offline' (sem sessão/uuid) ou 'error'."""
        if not uuid:
            return 'offline'
        try:
            geonetwork_service = getattr(self._dialog, 'geonetwork_service', None)
            if not geonetwork_service or not getattr(getattr(self._dialog, 'plugin', None), 'api_session', None):
                return 'offline'
            remote = geonetwork_service.fetch_from_geonetwork(uuid, config_loader)
            if not remote:
                return 'not_found'
            remote_date = remote.get('dateStamp') or ''
            if remote_date and local_date_stamp and remote_date > local_date_stamp:
                return 'update_available'
            return 'synced'
        except Exception as e:
            print(f"GeoMetadata [check_gn_sync]: {e}")
            return 'error'

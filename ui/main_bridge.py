# -*- coding: utf-8 -*-
"""
main_bridge.py — GeoMetadata Plugin
=====================================
Ponte de comunicação para a interface principal em HTML.
Exposto ao JS via QWebChannel como 'bridge'.
"""

import os
from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot
from ..core.plugin_config import config_loader

class MainBridge(QObject):
    """
    Ponte principal para o diálogo do plugin.
    Sinais JS -> Python e Python -> JS.
    """

    # Sinais emitidos para o JS
    nav_changed        = pyqtSignal(str)            # Notifica mudança de painel
    auth_status        = pyqtSignal(bool, str)      # (is_logged, username)
    form_data_req      = pyqtSignal('QVariant')     # Envia dados para preencher o form
    login_loading      = pyqtSignal(str)            # Mensagem de carregamento durante auth
    login_error        = pyqtSignal(str)            # Erro de autenticação
    layer_changed      = pyqtSignal(str)            # Nome da camada ativa mudou
    gn_contacts_ready   = pyqtSignal(str, str, 'QVariant')  # key, query, results
    gn_contact_enriched = pyqtSignal(str, int, 'QVariant')  # key, idx, enriched_data
    toast               = pyqtSignal(str, str, str)         # message, title, type
    gn_metadata_search_ready = pyqtSignal('QVariant')       # [{uuid, title, dateStamp}]
    gn_publish_succeeded = pyqtSignal(str)                  # uuid — publicação confirmada, badge -> Sincronizado
    local_save_succeeded = pyqtSignal(str)                  # uuid — save local (DB/sidecar) confirmado, recheca badge

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._form_manager = getattr(dialog, 'form_manager', None)
        self._sso_worker     = None
        self._adm_worker     = None
        self._gn_workers     = {}
        self._enrich_workers = []
        self._gn_search_worker = None
        try:
            plugin = getattr(dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(dialog, 'iface', None)
            if iface:
                iface.currentLayerChanged.connect(self._on_layer_changed)
        except Exception:
            pass

    def _on_layer_changed(self, layer):
        self.layer_changed.emit(layer.name() if layer else "")

    @pyqtSlot(result=str)
    def get_active_layer_name(self) -> str:
        """Retorna o nome da camada ativa no QGIS."""
        try:
            plugin = getattr(self._dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
            layer  = iface.activeLayer() if iface else None
            return layer.name() if layer else ""
        except Exception:
            return ""

    @pyqtSlot(result='QVariant')
    def list_layers(self):
        """Retorna lista de camadas carregadas no projeto QGIS atual."""
        try:
            from qgis.core import QgsProject, QgsRasterLayer
            layers = QgsProject.instance().mapLayers().values()
            result = []
            for l in layers:
                t = 'raster' if isinstance(l, QgsRasterLayer) else 'vector'
                result.append({'id': l.id(), 'name': l.name(), 'type': t})
            result.sort(key=lambda x: x['name'].lower())
            return result
        except Exception as e:
            print(f"GeoMetadata [list_layers]: {e}")
            return []

    @pyqtSlot(str)
    def set_active_layer(self, layer_id: str):
        """Define a camada ativa no painel de camadas do QGIS."""
        try:
            from qgis.core import QgsProject
            plugin = getattr(self._dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
            layer  = QgsProject.instance().mapLayer(layer_id)
            if layer and iface:
                iface.setActiveLayer(layer)
        except Exception as e:
            print(f"GeoMetadata [set_active_layer]: {e}")
        
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

    @pyqtSlot('QVariant')
    def save_metadata(self, form_data):
        """Salva o metadado (rascunho local). Recebe o dict do formulário HTML."""
        self._dialog.save_metadata(metadata_dict=form_data if isinstance(form_data, dict) else None)

    @pyqtSlot()
    def start_login(self):
        """Inicia autenticação SSO corporativa sem abrir diálogo Qt separado."""
        try:
            from ..core.env_checker import check_and_run_setup
            if not check_and_run_setup(parent=self._dialog):
                self.login_error.emit("Dependência MSAL não encontrada. Configure o ambiente primeiro.")
                return
            from ..core.plugin_config import config_loader
            from ..core.entra_auth_provider import EntraAuthProvider
            from .web_bridge import _SsoWorker
            entra_cfg = config_loader.get_entra_id_config()
            provider  = EntraAuthProvider(
                client_id=entra_cfg.get("client_id", ""),
                tenant_id=entra_cfg.get("tenant_id", ""),
                scopes=entra_cfg.get("scopes", ["User.Read"])
            )
            self.login_loading.emit("Aguardando autenticação no navegador...")
            self._sso_worker = _SsoWorker(provider)
            self._sso_worker.auth_success.connect(self._on_sso_success)
            self._sso_worker.auth_failed.connect(self._on_sso_failed)
            self._sso_worker.start()
        except Exception as e:
            self.login_error.emit(str(e))

    def _on_sso_success(self, provider):
        session = provider.get_session()
        username = provider.get_username() or "Usuário CDHU"
        self._dialog.plugin.api_session = session
        self._dialog.plugin.auth_username = username
        self._dialog.update_ui_for_login_status()

    def _on_sso_failed(self, msg):
        self.login_error.emit(msg)

    @pyqtSlot(str, str)
    def do_admin_login(self, user: str, password: str):
        """Login administrativo (usuário/senha GeoServer) sem abrir diálogo Qt separado."""
        try:
            from ..core.plugin_config import config_loader
            from .web_bridge import _AdminWorker
            geoserver_url = config_loader.get_geoserver_url()
            self.login_loading.emit("Verificando credenciais...")
            self._adm_worker = _AdminWorker(user, password, geoserver_url)
            self._adm_worker.login_success.connect(self._on_adm_success)
            self._adm_worker.login_failed.connect(self._on_adm_failed)
            self._adm_worker.start()
        except Exception as e:
            self.login_error.emit(str(e))

    def _on_adm_success(self, session, username):
        self._dialog.plugin.api_session = session
        self._dialog.plugin.auth_username = username
        self._dialog.update_ui_for_login_status()

    def _on_adm_failed(self, msg):
        self.login_error.emit(msg)

    @pyqtSlot()
    def logout(self):
        """Encerra a sessão do usuário."""
        self._dialog.plugin.api_session = None
        self._dialog.plugin.auth_username = None
        self._dialog.update_ui_for_login_status()

    @pyqtSlot('QVariant')
    def export_xml(self, form_data):
        """Exporta metadados para XML local. Recebe o dict do formulário HTML."""
        self._dialog.exportar_to_xml(metadata_dict=form_data if isinstance(form_data, dict) else None)

    @pyqtSlot('QVariant')
    def export_geohab(self, form_data):
        """Publica o metadado no GeoNetwork. Recebe o dict do formulário HTML."""
        self._dialog.exportar_to_geo(metadata_dict=form_data if isinstance(form_data, dict) else None)

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
            "is_logged": is_logged,
            "cda_url": config_loader.get_cda_url()
        }

    @pyqtSlot(result='QVariant')
    def get_layer_info(self):
        """Retorna SRC e extensão geográfica (WGS84) da camada ativa no QGIS."""
        try:
            from qgis.core import (QgsCoordinateTransform,
                                   QgsCoordinateReferenceSystem,
                                   QgsProject)
            plugin = getattr(self._dialog, 'plugin', None)
            iface  = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
            layer  = iface.activeLayer() if iface else None
            if not layer:
                return None
            crs     = layer.crs()
            auth_id = crs.authid()
            desc    = crs.description()
            result  = {'code': auth_id, 'title': desc + ' (' + auth_id + ')'}
            extent  = layer.extent()
            if not extent.isEmpty():
                wgs84     = QgsCoordinateReferenceSystem('EPSG:4326')
                transform = QgsCoordinateTransform(crs, wgs84, QgsProject.instance())
                wgs_ext   = transform.transformBoundingBox(extent)
                result['north'] = round(wgs_ext.yMaximum(), 6)
                result['south'] = round(wgs_ext.yMinimum(), 6)
                result['east']  = round(wgs_ext.xMaximum(), 6)
                result['west']  = round(wgs_ext.xMinimum(), 6)
            return result
        except Exception:
            return None

    # ── Contatos do usuário (persistidos localmente) ──────────────────────────

    def _user_contacts_path(self) -> str:
        import os
        try:
            from qgis.core import QgsApplication
            base = QgsApplication.qgisSettingsDirPath()
        except Exception:
            base = os.path.expanduser('~')
        return os.path.join(base, 'geometadata_user_contacts.json')

    def _load_user_contacts(self) -> list:
        import json, os
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
        from .web_bridge import _GnContactsWorker
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
        from .web_bridge import _GnContactEnrichWorker
        records_url = config_loader.get_geonetwork_url().get('records_url', '')
        if not records_url:
            return
        worker = _GnContactEnrichWorker(session, uuid, records_url, section_key, idx)
        worker.done.connect(lambda k, i, d: self.gn_contact_enriched.emit(k, i, d))
        self._enrich_workers.append(worker)
        worker.start()

    # Cache de camadas do GeoServer (carregado uma vez por sessão)
    _geoserver_layers_cache = None

    @pyqtSlot(str, result='QVariant')
    def search_geoserver(self, query: str):
        """Busca camadas públicas no GeoServer via WMS GetCapabilities (sem autenticação)."""
        try:
            import ssl
            import urllib.request
            import xml.etree.ElementTree as ET
            from ..core.plugin_config import config_loader

            base_url = config_loader.get_geoserver_url().rstrip('/')
            if not base_url:
                print("GeoMetadata [search_geoserver]: geoserver_url não configurado.")
                return []

            is_logged = getattr(getattr(self._dialog, 'plugin', None), 'api_session', None) is not None

            if MainBridge._geoserver_layers_cache is None:
                caps_url = f"{base_url}/wms?service=WMS&version=1.3.0&request=GetCapabilities"
                print(f"GeoMetadata [search_geoserver]: carregando capabilities de {caps_url}")

                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode    = ssl.CERT_NONE

                req = urllib.request.Request(caps_url, headers={'User-Agent': 'GeoMetadataPlugin/1.0'})
                with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                    content = resp.read()

                print(f"GeoMetadata [search_geoserver]: {len(content)} bytes recebidos.")

                root = ET.fromstring(content)
                all_layers = []

                for layer_el in root.iter():
                    tag_local = layer_el.tag.split('}')[-1] if '}' in layer_el.tag else layer_el.tag
                    if tag_local != 'Layer':
                        continue
                    name_el = title_el = None
                    for child in layer_el:
                        ct = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        if ct == 'Name'  and name_el  is None: name_el  = child
                        if ct == 'Title' and title_el is None: title_el = child
                    name  = (name_el.text  or '').strip() if name_el  is not None else ''
                    title = (title_el.text or '').strip() if title_el is not None else ''
                    if not name or ':' not in name:
                        continue
                    workspace = name.split(':', 1)[0]
                    all_layers.append({
                        'name':      name,
                        'workspace': workspace,
                        'title':     title or name,
                        'wms_url':   f"{base_url}/{workspace}/wms?service=WMS",
                        'wfs_url':   f"{base_url}/{workspace}/wfs?service=WFS",
                    })

                MainBridge._geoserver_layers_cache = all_layers
                print(f"GeoMetadata [search_geoserver]: {len(all_layers)} camadas indexadas.")

            q = query.lower().strip()
            cache = MainBridge._geoserver_layers_cache
            results = [l for l in cache if q in l['name'].lower() or q in l['title'].lower()][:25]

            for r in results:
                r['wfs_available'] = is_logged

            return results

        except Exception as e:
            import traceback
            print(f"GeoMetadata [search_geoserver] ERRO: {e}")
            traceback.print_exc()
            return []

    @pyqtSlot(str)
    def open_file_location(self, file_path: str):
        """Abre o Explorer na pasta do arquivo, com o arquivo já selecionado/destacado."""
        import os
        import subprocess
        try:
            norm_path = os.path.normpath(file_path)
            if os.name == 'nt':
                # Forma de string (não lista) é a que funciona de forma confiável com
                # caminhos com espaço — o explorer.exe faz seu próprio parsing da linha
                # de comando, então as aspas em volta do caminho precisam chegar literais.
                subprocess.Popen(f'explorer /select,"{norm_path}"')
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(norm_path)])
        except Exception as e:
            print(f"GeoMetadata [open_file_location]: {e}")

    @pyqtSlot(str, str)
    def export_contact_xml(self, xml_string: str, filename: str):
        """Salva o XML de sub-template de contato (ISO 19139) em arquivo escolhido pelo usuário."""
        import os
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
        from .web_bridge import _GnRecordSearchWorker
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
            metadata_service = getattr(self._dialog, 'metadata_service', None)
            if not metadata_service:
                return None
            return metadata_service.fetch_from_geonetwork(uuid, config_loader)
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
            metadata_service = getattr(self._dialog, 'metadata_service', None)
            if not metadata_service or not getattr(getattr(self._dialog, 'plugin', None), 'api_session', None):
                return 'offline'
            remote = metadata_service.fetch_from_geonetwork(uuid, config_loader)
            if not remote:
                return 'not_found'
            remote_date = remote.get('dateStamp') or ''
            if remote_date and local_date_stamp and remote_date > local_date_stamp:
                return 'update_available'
            return 'synced'
        except Exception as e:
            print(f"GeoMetadata [check_gn_sync]: {e}")
            return 'error'

    @pyqtSlot()
    def clear_draft(self):
        """Remove só o rascunho da camada ativa — não mexe nos drafts de outras camadas."""
        try:
            drafts = self._load_all_drafts()
            if drafts.pop(self._layer_key(), None) is not None:
                self._save_all_drafts(drafts)
        except Exception as e:
            print(f"GeoMetadata [clear_draft]: {e}")

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

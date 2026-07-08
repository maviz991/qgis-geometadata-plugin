# -*- coding: utf-8 -*-
"""
web_bridge.py — GeoMetadata Plugin
=====================================
Objeto Python exposto ao JavaScript via QWebChannel.
Atua como ponte bidirecional entre a UI HTML e a lógica Python do plugin.

Padrão de uso no JS:
    new QWebChannel(qt.webChannelTransport, function(channel) {
        var bridge = channel.objects.bridge;
        bridge.sso_failed.connect(function(msg) { ... });
        bridge.start_sso();
    });
"""

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot

from ..core.entra_auth_provider import EntraAuthProvider, is_msal_available
from ..core.dependency_installer import DependencyInstaller
from ..core.plugin_config import config_loader


# ---------------------------------------------------------------------------
# Workers (reutilizados do login_dialog.py anterior)
# ---------------------------------------------------------------------------
from qgis.PyQt.QtCore import QThread


class _SsoWorker(QThread):
    auth_success = pyqtSignal(object)   # EntraAuthProvider
    auth_failed  = pyqtSignal(str)

    def __init__(self, provider: EntraAuthProvider):
        super().__init__()
        self._provider = provider

    def run(self):
        try:
            if self._provider.authenticate_interactive():
                self.auth_success.emit(self._provider)
            else:
                self.auth_failed.emit(self._provider.get_error() or "Autenticação cancelada.")
        except Exception as e:
            self.auth_failed.emit(str(e))


class _GnContactsWorker(QThread):
    done = pyqtSignal(str, str, list)  # key, query, results

    def __init__(self, session, key: str, query: str, gn_base_url: str):
        super().__init__()
        self._session  = session
        self._key      = key
        self._query    = query
        self._gn_url   = gn_base_url.rstrip('/')

    def run(self):
        import re as _re
        try:
            # GeoNetwork armazena contatos como sub-templates (isTemplate="s")
            # O endpoint correto é o Elasticsearch do GN4
            es_url  = f"{self._gn_url}/srv/api/search/records/_search"
            payload = {"size": 100, "query": {"term": {"isTemplate": "s"}}}
            resp = self._session.post(es_url, json=payload, timeout=5, verify=False,
                                      headers={'Accept': 'application/json'})
            if resp.status_code != 200:
                self.done.emit(self._key, self._query, [])
                return

            hits = resp.json().get('hits', {}).get('hits', [])
            q    = self._query.lower().strip()
            results = []
            for hit in hits:
                src   = hit.get('_source', {})
                title = (src.get('resourceTitleObject') or {}).get('default', '') or ''

                sigla_m = _re.search(r'\((.*?)\)', title)
                sigla   = sigla_m.group(1).strip() if sigla_m else ''
                org     = (src.get('Org') or '').strip() or (
                    title.replace(f" ({sigla})", "").strip() if sigla else title.strip()
                )
                email   = (src.get('email') or '').strip()
                uuid    = src.get('uuid', '')

                if not org and not email:
                    continue
                if q and not (q in org.lower() or q in email.lower() or q in sigla.lower()):
                    continue

                results.append({
                    'sigla':    sigla,
                    'org':      org,
                    'email':    email,
                    'position': '',
                    'phone':    '',
                    'address':  '', 'city': '', 'state': '', 'zip': '', 'country': 'Brasil',
                    'role':     'pointOfContact',
                    '_source':  'gn',
                    '_gn_uuid': uuid,
                })
            self.done.emit(self._key, self._query, results)
        except Exception as exc:
            print(f"GeoMetadata [GnContactsWorker]: {exc}")
            self.done.emit(self._key, self._query, [])


class _GnRecordSearchWorker(QThread):
    """Busca registros de metadado (não subtemplates de contato) no GN por título,
    pra alimentar o fluxo de 'Puxar do Geohab' do editor."""
    done = pyqtSignal(list)  # [{uuid, title, dateStamp}]

    def __init__(self, session, query: str, gn_base_url: str):
        super().__init__()
        self._session = session
        self._query   = query
        self._gn_url  = gn_base_url.rstrip('/')

    def run(self):
        try:
            es_url  = f"{self._gn_url}/srv/api/search/records/_search"
            payload = {
                "size": 20,
                "query": {"bool": {"must": [
                    {"term": {"isTemplate": "n"}},
                    {"match": {"resourceTitleObject.default": self._query}}
                ]}}
            }
            resp = self._session.post(es_url, json=payload, timeout=8, verify=False,
                                      headers={'Accept': 'application/json'})
            if resp.status_code != 200:
                self.done.emit([])
                return

            hits = resp.json().get('hits', {}).get('hits', [])
            results = []
            for hit in hits:
                src = hit.get('_source', {})
                title = (src.get('resourceTitleObject') or {}).get('default', '') or ''
                uuid = src.get('uuid', '')
                if not uuid or not title:
                    continue
                results.append({
                    'uuid': uuid,
                    'title': title,
                    'dateStamp': src.get('changeDate', ''),
                })
            self.done.emit(results)
        except Exception as exc:
            print(f"GeoMetadata [GnRecordSearchWorker]: {exc}")
            self.done.emit([])


class _GnContactEnrichWorker(QThread):
    """Busca o XML de um sub-template de contato do GeoNetwork e extrai todos os campos."""
    done = pyqtSignal(str, int, dict)  # section_key, idx, enriched_data

    def __init__(self, session, uuid: str, records_url: str, section_key: str, idx: int):
        super().__init__()
        self._session  = session
        self._url      = f"{records_url}/{uuid}/formatters/xml"
        self._key      = section_key
        self._idx      = idx

    def run(self):
        import re as _re
        try:
            resp = self._session.get(self._url, timeout=5, verify=False)
            if resp.status_code != 200:
                self.done.emit(self._key, self._idx, {})
                return
            xml = resp.text

            def _x(pattern):
                m = _re.search(pattern, xml, _re.DOTALL)
                return m.group(1).strip() if m else ''

            data = {
                'role':     _x(r'CI_RoleCode[^>]*codeListValue="([^"]+)"'),
                'sigla':    _x(r'<gmd:individualName>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
                'org':      _x(r'<gmd:organisationName>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
                'position': _x(r'<gmd:positionName>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
                'phone':    _x(r'<gmd:voice>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
                'email':    _x(r'<gmd:electronicMailAddress>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
                'address':  _x(r'<gmd:deliveryPoint>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
                'city':     _x(r'<gmd:city>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
                'state':    _x(r'<gmd:administrativeArea>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
                'zip':      _x(r'<gmd:postalCode>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
                'country':  _x(r'<gmd:country>.*?<gco:CharacterString>([^<]+)</gco:CharacterString>'),
            }
            self.done.emit(self._key, self._idx, {k: v for k, v in data.items() if v})
        except Exception as exc:
            print(f"GeoMetadata [GnContactEnrichWorker]: {exc}")
            self.done.emit(self._key, self._idx, {})


class _AdminWorker(QThread):
    login_success = pyqtSignal(object, str)   # session, username
    login_failed  = pyqtSignal(str)

    def __init__(self, user: str, password: str, geoserver_url: str):
        super().__init__()
        self._user     = user
        self._password = password
        self._url      = f"{geoserver_url.rstrip('/')}/ows?version=1.3.0"

    def run(self):
        try:
            session        = requests.Session()
            session.verify = False
            session.auth   = (self._user, self._password)
            resp = session.get(self._url, timeout=12)
            if resp.status_code == 401:
                self.login_failed.emit("Usuário ou senha inválidos.")
            elif resp.status_code == 403:
                self.login_failed.emit("Acesso negado. Verifique as permissões do usuário.")
            else:
                self.login_success.emit(session, self._user)
        except requests.exceptions.ConnectionError:
            self.login_failed.emit("Sem conexão com o servidor. Verifique a rede ou VPN.")
        except requests.exceptions.Timeout:
            self.login_failed.emit("Servidor não respondeu. Tente novamente.")
        except Exception as e:
            self.login_failed.emit(str(e))


# ---------------------------------------------------------------------------
# Bridge principal
# ---------------------------------------------------------------------------
class LoginBridge(QObject):
    """
    Exposto ao JS como `channel.objects.bridge`.

    Sinais Python → JS (conectar via bridge.<signal>.connect(...) no JS):
        sso_status(msg: str)     — mensagem de status durante o fluxo SSO
        sso_failed(msg: str)     — SSO falhou
        admin_failed(msg: str)   — login admin falhou
        install_status(msg: str) — progresso da instalação do msal
        install_done()           — msal instalado, reiniciar QGIS
        install_error(msg: str)  — instalação falhou

    Slots JS → Python (chamar via bridge.<slot>(...) no JS):
        get_msal_state() -> bool
        start_sso()
        start_admin(user, password)
        run_install()
        cancel()
    """

    # Sinais emitidos para o JS
    sso_status     = pyqtSignal(str)
    sso_failed     = pyqtSignal(str)
    admin_failed   = pyqtSignal(str)
    install_status = pyqtSignal(str)
    install_done   = pyqtSignal()
    install_error  = pyqtSignal(str)

    def __init__(self, client_id: str, tenant_id: str, scopes: list,
                 geoserver_url: str, dialog, parent=None):
        super().__init__(parent)
        self._client_id     = client_id
        self._tenant_id     = tenant_id
        self._scopes        = scopes
        self._geoserver_url = geoserver_url
        self._dialog        = dialog   # referência ao LoginDialog (QDialog)

        # Resultado do login — lido pelo dialog após accept()
        self.session:  object = None
        self.username: str    = ""

        self._sso_worker  = None
        self._adm_worker  = None
        self._installer   = None

    # ------------------------------------------------------------------
    # Slots expostos ao JS
    # ------------------------------------------------------------------

    @pyqtSlot(result=bool)
    def get_msal_state(self) -> bool:
        return is_msal_available()

    @pyqtSlot()
    def start_sso(self):
        self.sso_status.emit("Aguardando login no navegador...")
        provider = EntraAuthProvider(self._client_id, self._tenant_id, self._scopes)
        self._sso_worker = _SsoWorker(provider)
        self._sso_worker.auth_success.connect(self._on_sso_ok)
        self._sso_worker.auth_failed.connect(self._on_sso_fail)
        self._sso_worker.start()

    @pyqtSlot(str, str)
    def start_admin(self, user: str, password: str):
        self._adm_worker = _AdminWorker(user, password, self._geoserver_url)
        self._adm_worker.login_success.connect(self._on_admin_ok)
        self._adm_worker.login_failed.connect(self._on_admin_fail)
        self._adm_worker.start()

    @pyqtSlot()
    def run_install(self):
        self.install_status.emit("Instalando msal, aguarde...")
        self._installer = DependencyInstaller("msal")
        self._installer.install_success.connect(self._on_install_ok)
        self._installer.install_failed.connect(self._on_install_fail)
        self._installer.start()

    @pyqtSlot()
    def cancel(self):
        self._dialog.reject()

    # ------------------------------------------------------------------
    # Callbacks internos (GUI thread via signal/slot)
    # ------------------------------------------------------------------

    def _on_sso_ok(self, provider: EntraAuthProvider):
        self.session  = provider.get_session()
        self.username = provider.get_username()
        self._dialog.accept()

    def _on_sso_fail(self, msg: str):
        self.sso_failed.emit(msg)

    def _on_admin_ok(self, session, username: str):
        self.session  = session
        self.username = username
        self._dialog.accept()

    def _on_admin_fail(self, msg: str):
        self.admin_failed.emit(msg)

    def _on_install_ok(self, _pkg: str):
        self.install_done.emit()

    def _on_install_fail(self, _pkg: str, err: str):
        self.install_error.emit(
            f"Falha na configuração automática.<br><br>"
            f"Por favor, abra um ticket no <b>CDA</b>: "
            f"<a href='{config_loader.get_cda_url()}'>cda.cdhu.sp.gov.br</a>"
        )

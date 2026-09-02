# -*- coding: utf-8 -*-
"""
geonetwork_workers.py - GeoMetadata Plugin
=====================================
Workers (QThread) usados só pelo GeoNetworkBridge - busca de contatos,
busca de registros de metadado, enriquecimento de contato via GN, e
publicação (RNF02 - chamadas de rede não podem travar a UI do QGIS).
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal

# Overrides built-in print for this module to prevent QGIS segfaults from background threads
# (mesmo fix de ui/geoserver_workers.py - _GnSyncCheckWorker e as demais QThreads deste
# módulo têm o mesmo padrão de print() direto em run(), exposto ao mesmo crash).
def print(*args, **kwargs):
    pass


class _GnPublishWorker(QThread):
    """Publica o XML no GeoNetwork e busca de volta o dateStamp real que o GN carimbou -
    as duas chamadas de rede do fluxo de publicação, isoladas da UI thread. Só usa
    core/geonetwork_service.py (requests puro, sem QtWidgets) - seguro rodar em thread,
    diferente do PersistenceService (que abre QMessageBox nativo e por isso continua
    rodando na thread principal)."""
    done = pyqtSignal(str, str, str)  # uuid_criado, date_stamp, error_message ('' se ok)

    def __init__(self, geonetwork_service, xml_payload: str, config_loader_instance, uuid_processing: str):
        super().__init__()
        self._service = geonetwork_service
        self._xml_payload = xml_payload
        self._config = config_loader_instance
        self._uuid_processing = uuid_processing

    def run(self):
        try:
            uuid_criado = self._service.push_to_geonetwork(self._xml_payload, self._config, self._uuid_processing)
            date_stamp = ''
            if uuid_criado:
                try:
                    remote = self._service.fetch_from_geonetwork(uuid_criado, self._config)
                    if remote and remote.get('dateStamp'):
                        date_stamp = remote['dateStamp']
                except Exception:
                    pass  # não crítico - sync check refaz essa consulta depois
            self.done.emit(uuid_criado or '', date_stamp, '')
        except Exception as exc:
            self.done.emit('', '', str(exc))


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
            # Mesmo padrão do _GnContactsWorker: busca um lote amplo sem filtro de texto
            # no Elasticsearch (um `match` não lida bem com termos curtos de 2-3 letras,
            # que é o caso comum aqui) e filtra por substring do lado de cá.
            es_url  = f"{self._gn_url}/srv/api/search/records/_search"
            payload = {"size": 100, "query": {"term": {"isTemplate": "n"}}}
            resp = self._session.post(es_url, json=payload, timeout=8, verify=False,
                                      headers={'Accept': 'application/json'})
            if resp.status_code != 200:
                self.done.emit([])
                return

            hits = resp.json().get('hits', {}).get('hits', [])
            q = self._query.lower().strip()
            results = []
            for hit in hits:
                src = hit.get('_source', {})
                title = (src.get('resourceTitleObject') or {}).get('default', '') or ''
                uuid = src.get('uuid', '')
                if not uuid or not title:
                    continue
                if q and q not in title.lower():
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


class _GnSyncCheckWorker(QThread):
    """Nível sistema de check_gn_sync (GeoNetworkBridge) isolado da UI thread - é a única
    chamada de rede desse método (fetch_from_geonetwork, com possível warm-up de sessão
    antes), antes rodava direto no pyqtSlot e travava a UI (Qt event loop, inclusive a
    QWebEngineView) a cada troca de camada com usuário logado.

    Compara CONTEÚDO (título/resumo/palavras-chave) entre o que está de fato publicado no
    Geohab agora (`remote`) e o que sabemos ter salvo localmente (`local_snapshot`, dict no
    formato de xml_parser.parse_xml_to_dict) - não só o campo dateStamp. Mesmo espírito do
    GeoServer (`_GsSyncCheckWorker`, geoserver_workers.py): comparar timestamp sozinho é
    frágil (não muda com toda edição de campo, e pode ter formato/precisão diferente entre
    o que o form local guarda e o que o GN carimba) - "Atualização disponível" precisa
    refletir se o CONTEÚDO mudou, não só uma data."""
    done = pyqtSignal(str, str)  # state, layer_name

    def __init__(self, geonetwork_service, uuid: str, local_snapshot: dict, config_loader_instance, layer_name: str):
        super().__init__()
        self._service = geonetwork_service
        self._uuid = uuid
        self._local_snapshot = local_snapshot or {}
        self._config = config_loader_instance
        self._layer_name = layer_name

    def run(self):
        try:
            remote = self._service.fetch_from_geonetwork(self._uuid, self._config)
            if not remote:
                print(f"GeoMetadata [_GnSyncCheckWorker] uuid={self._uuid!r} não encontrado no Geohab -> sys_not_found")
                self.done.emit('sys_not_found', self._layer_name)
                return
            remote_title = (remote.get('title') or '').strip()
            remote_abstract = (remote.get('abstract') or '').strip()
            remote_keywords = sorted(remote.get('MD_Keywords') or [])
            local_title = (self._local_snapshot.get('title') or '').strip()
            local_abstract = (self._local_snapshot.get('abstract') or '').strip()
            local_keywords = sorted(self._local_snapshot.get('MD_Keywords') or [])
            diverges = (
                remote_title != local_title or
                remote_abstract != local_abstract or
                remote_keywords != local_keywords
            )
            print(
                f"GeoMetadata [_GnSyncCheckWorker] uuid={self._uuid!r} diverges={diverges} "
                f"remote_title={remote_title!r} local_title={local_title!r} "
                f"remote_dateStamp={remote.get('dateStamp')!r} local_dateStamp={self._local_snapshot.get('dateStamp')!r}"
            )
            if diverges:
                self.done.emit('sys_update_available', self._layer_name)
                return
            self.done.emit('sys_synced', self._layer_name)
        except Exception as exc:
            print(f"GeoMetadata [check_gn_sync] nível sistema: {exc}")
            self.done.emit('error', self._layer_name)


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

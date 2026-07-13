# -*- coding: utf-8 -*-
"""
geonetwork_workers.py — GeoMetadata Plugin
=====================================
Workers (QThread) usados só pelo GeoNetworkBridge — busca de contatos,
busca de registros de metadado, enriquecimento de contato via GN, e
publicação (RNF02 — chamadas de rede não podem travar a UI do QGIS).
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal


class _GnPublishWorker(QThread):
    """Publica o XML no GeoNetwork e busca de volta o dateStamp real que o GN carimbou —
    as duas chamadas de rede do fluxo de publicação, isoladas da UI thread. Só usa
    core/geonetwork_service.py (requests puro, sem QtWidgets) — seguro rodar em thread,
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
                    pass  # não crítico — sync check refaz essa consulta depois
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

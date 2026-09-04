# -*- coding: utf-8 -*-
"""
status_workers.py - GeoMetadata Plugin
=====================================
Worker (QThread) usado só pelo badge de status dos cards da Home
(MainBridge.check_services_status) - ping simples, sem exigir login, pra
saber se o GeoNetwork/GeoServer estão respondendo (RNF02: chamada de rede
fora da UI thread).
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal

try:
    import requests
except ImportError:
    requests = None

# Overrides built-in print pra evitar crash nativo do QGIS - mesmo motivo de
# geoserver_workers.py/geonetwork_workers.py (ver docs_projeto/bugs.md, Bug 41): chamar
# print() de dentro de run() (QThread de background) já causou o QGIS inteiro fechar sem
# crash dump nesse ambiente. Este módulo (status_workers.py) tinha ficado de fora dos dois
# quando o Bug 41 corrigiu os outros dois - print() aqui roda toda vez que o ping de
# status da Home (check_services_status) recebe algo != 200 ou uma exceção de rede
# (comum logo após reiniciar/recarregar o plugin, quando um dos serviços ainda não
# respondeu de forma limpa).
def print(*args, **kwargs):
    pass


class _ServiceStatusWorker(QThread):
    """Verificação simples, sem exigir login (serve tanto deslogado quanto logado) - só
    confirma se dá pra acessar a URL base do serviço (.../geoserver ou .../geonetwork) e
    ela responde. Classifica em 4 estados:
      'active'      - respondeu com status 200 (exatamente - "acessou normal" de verdade).
      'unstable'    - respondeu, mas com outro código (redirect que não fechou em 200, 4xx,
                      outro 5xx, etc.) - o servidor está de pé, mas não do jeito esperado.
      'unavailable' - respondeu 503 - o próprio gateway/proxy avisando que o backend real
                      está fora do ar agora, classe própria (não é só "instável", nem é
                      "offline" - a conexão de rede em si funcionou).
      'offline'     - não respondeu nada (timeout, conexão recusada, DNS, SSL, etc.)."""
    done = pyqtSignal(str, str)  # service ('geonetwork'|'geoserver'), status

    _TIMEOUT_S = 6

    def __init__(self, service: str, url: str):
        super().__init__()
        self._service = service
        self._url = url

    def run(self):
        if not requests or not self._url:
            self.done.emit(self._service, 'offline')
            return
        try:
            resp = requests.get(self._url, timeout=self._TIMEOUT_S, verify=False)
            if resp.status_code == 200:
                status = 'active'
            elif resp.status_code == 503:
                # 503 é o próprio gateway/proxy avisando que o backend real está fora do ar
                # (diferente de um 401/403/redirect/outro 5xx, onde algo respondeu mas só não
                # do jeito esperado) - classe própria, não "instável" (não é só devagar/com
                # erro) nem "offline" (a rede respondeu, só não com o serviço de pé).
                print(f"GeoMetadata [_ServiceStatusWorker] {self._service} ({self._url!r}): status 503")
                status = 'unavailable'
            else:
                # Servidor respondeu, só não com 200 (ex.: redirect pra uma página de erro
                # do gateway, 401/403 num endpoint que não deveria exigir isso, outro 5xx) -
                # ainda é "está de pé", mas não o esperado -> instável, não offline.
                print(f"GeoMetadata [_ServiceStatusWorker] {self._service} ({self._url!r}): status {resp.status_code}")
                status = 'unstable'
        except requests.exceptions.RequestException as exc:
            # Diagnóstico - "Offline" pode estar certo (servidor de fato fora do ar), mas
            # também pode ser um SSLError intermitente já visto neste ambiente antes (ver
            # docs_projeto/bugs.md - "[EVP: INVALID_KEY_LENGTH] invalid key length" contra
            # este mesmo host), que não significa o servidor estar fora do ar. Sem esse
            # print não dava pra distinguir "offline de verdade" de "erro de rede local".
            print(f"GeoMetadata [_ServiceStatusWorker] {self._service} ({self._url!r}): {exc}")
            status = 'offline'
        self.done.emit(self._service, status)

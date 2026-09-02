# -*- coding: utf-8 -*-
"""
http_lock.py - GeoMetadata Plugin
=====================================
Lock global compartilhado entre GeoNetworkService e GeoServerService.

Depois de um login local (LOGIN UNIFICADO/admin, ver GeoMetadata.py e
ui/main_bridge.py:do_admin_login), gs_rest_session nunca é preenchida - só
api_session. GeoServerService._get_rest_session() cai então no fallback e usa
EXATAMENTE a mesma requests.Session de GeoNetworkService (self.plugin.api_session).

Vários workers (QThread) de domínios diferentes podem disparar chamadas de rede quase
juntos - o caso mais comum é logo após o login, quando _onAuthStateChangedForSync (JS)
dispara ao mesmo tempo a checagem de sincronismo do GN (_GnSyncCheckWorker) e a
info/checagem da camada ativa do GS (_GsActiveLayerInfoWorker, que também chama
fetch_from_geonetwork internamente) - cada um na sua própria QThread. Sem proteção
nenhuma, as duas acabavam chamando .get()/.post()/.put() na MESMA instância de
requests.Session ao mesmo tempo. requests/urllib3 não garante segurança sob chamadas
verdadeiramente concorrentes de múltiplas threads (histórico de corrupção do pool de
conexões/estado SSL, sobretudo com verify=False como usado em todo o projeto) - na
prática isso se manifestava como crash nativo do processo inteiro (QGIS fechava sem
traceback Python, sem padrão fixo - dependia do timing exato da corrida).

Este lock serializa toda chamada de rede que passa pela sessão compartilhada,
eliminando a concorrência real na raiz. O custo é uma pequena espera quando duas
checagens em background calham de disparar juntas - bem mais barato que o crash.
"""
import threading

HTTP_SESSION_LOCK = threading.Lock()

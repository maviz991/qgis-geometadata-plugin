# -*- coding: utf-8 -*-
"""
geoserver_bridge.py - GeoMetadata Plugin
=====================================
Ponte de comunicação específica do GeoServer (busca de camadas hoje;
publicação de camadas/workspaces nas próximas fases - ver requisitos_v2.md).
Exposto ao JS via QWebChannel como 'gsBridge'.
"""

import os
import time

from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot


class GeoServerBridge(QObject):
    """
    Ponte GeoServer para o diálogo do plugin.
    Sinais JS -> Python e Python -> JS específicos do GeoServer.
    """

    gs_workspaces_ready = pyqtSignal(list, str)  # workspaces, error
    gs_datastores_ready = pyqtSignal(list, str)  # datastores, error
    gs_featuretypes_ready = pyqtSignal(list, str)  # nomes de tabela visíveis no datastore, error
    gs_find_datastore_progress = pyqtSignal(str)  # mensagem de status da varredura
    gs_find_datastore_done = pyqtSignal(list, str)  # [{'workspace':..,'datastore':..}, ...], error
    gs_publish_done = pyqtSignal(bool, str, str, str, str)  # sucesso, mensagem (erro OU aviso de estilo), nome_publicado, wms_url, wfs_url
    gs_metadata_updated = pyqtSignal(bool, str)  # sucesso, mensagem - ver update_layer_metadata
    gs_destination_saved = pyqtSignal(bool)  # db_ok - "Continuar Depois" do painel GeoServer
    gs_sync_checked = pyqtSignal('QVariant')  # resultado de check_gs_sync (ver _GsSyncCheckWorker)
    gs_styles_ready = pyqtSignal(list, str)  # [{'name':..., 'workspace': ''|ws}], error - ver list_styles
    gs_layer_pulled = pyqtSignal(bool, 'QVariant', str)  # sucesso, dados, erro - "Serviços > Baixar Camada" (ver pull_layer_from_server)
    gs_rest_configured = pyqtSignal(bool, str)  # ok, username - resultado de configure_gs_rest_credentials
    gs_layer_info_ready = pyqtSignal('QVariant')  # resultado de get_active_layer_publish_info (ver _GsActiveLayerInfoWorker)
    gs_search_ready = pyqtSignal(list, str)  # camadas (filtradas pela query), erro - ver search_geoserver

    # Cache de camadas do GeoServer (carregado uma vez por sessão)
    _geoserver_layers_cache = None

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._workspaces_worker = None
        self._datastores_worker = None
        self._featuretypes_worker = None
        self._find_datastore_worker = None
        self._publish_worker = None
        # Lista (não slot único) - check_gs_sync pode ser chamado de novo (troca de camada,
        # retry) antes do worker anterior terminar; guardar só a última instância sobrescrevia
        # a referência Python da QThread em voo, o PyQt descartava o objeto órfão e o sinal
        # 'done' dela nunca chegava a emitir gs_sync_checked - o badge ficava preso até a
        # próxima revisita/checagem sem concorrência. Ver check_gs_sync.
        self._sync_check_workers = []
        # Idem - get_active_layer_publish_info pode ser chamado de novo (troca rápida de
        # camada, ou pelo badge combinado do editor GN, checkGsPublishStatus) antes do
        # worker anterior terminar. Ver _GsActiveLayerInfoWorker/get_active_layer_publish_info.
        self._layer_info_workers = []
        self._styles_worker = None
        self._gs_rest_worker = None
        self._pull_layer_worker = None
        self._pull_by_wms_worker = None
        self._update_metadata_worker = None
        self._search_layers_worker = None
        self._pending_search_query = None  # ver search_geoserver
        self._last_db_offline_notice = 0.0  # ver _notify_db_offline


    _DB_OFFLINE_NOTICE_INTERVAL = 60  # segundos - mesmo throttle de GeoNetworkBridge._notify_db_offline

    @staticmethod
    def _worker_busy(worker):
        """True se `worker` (QThread de slot único, não uma das listas _sync_check_workers/
        _layer_info_workers) ainda está rodando. Usado como guarda de reentrância antes de
        sobrescrever a referência: sem isso, um duplo clique (ou qualquer chamada repetida
        antes da anterior terminar) sobrescreve o atributo com uma QThread nova enquanto a
        antiga ainda executa - sem parent Qt e sem mais nenhuma referência Python, o GC
        destrói a QThread ainda em execução, e o Qt chama std::terminate(), fechando o QGIS
        inteiro sem crash dump (mesma causa raiz de MainBridge.do_admin_login/LoginBridge.
        start_admin/start_sso, ver docs_projeto/bugs.md Bug 35 - nunca replicada aqui até
        agora, apesar de todo worker de slot único desta classe estar exposto ao mesmo risco)."""
        return worker is not None and worker.isRunning()

    def _notify_db_offline(self):
        """Avisa o usuário (toast, throttlado) que o banco PostgreSQL desta camada está
        inacessível agora - mesma razão/throttle de GeoNetworkBridge._notify_db_offline
        (geonetwork_bridge.py): antes, uma falha de conexão (psycopg2.OperationalError) em
        fetch_saved_records era engolida e devolvia (None, None), indistinguível de "nada
        salvo pra essa camada"."""
        now = time.time()
        if now - self._last_db_offline_notice < self._DB_OFFLINE_NOTICE_INTERVAL:
            return
        self._last_db_offline_notice = now
        self._dialog.show_toast(
            'Banco de Dados Inacessível',
            'Não foi possível conectar ao banco PostgreSQL desta camada agora. Verifique a rede/VPN - até a conexão voltar, o status de sincronização pode não refletir o que está de fato salvo.',
            'warning'
        )

    @pyqtSlot(str, str)
    def configure_gs_rest_credentials(self, user: str, password: str):
        """Configura credenciais admin separadas exclusivamente para chamadas REST do
        GeoServer - necessário quando o usuário está autenticado via EntraID (SSO), mas o
        Bearer token Azure AD é rejeitado pela API REST do GeoOrchestra (401). Essas
        credenciais ficam só em memória (não persistidas em disco), na sessão ativa.
        Emite gs_rest_configured(True, username) em caso de sucesso, (False, mensagem) em
        caso de falha (credenciais inválidas ou servidor inacessível)."""
        if not user or not password:
            self.gs_rest_configured.emit(False, '[UI-001] Usuário e senha são obrigatórios.')
            return
        if self._worker_busy(self._gs_rest_worker):
            return
        from ..core.plugin_config import config_loader
        from .web_bridge import _AdminWorker
        geoserver_url = config_loader.get_geoserver_url()
        self._gs_rest_worker = _AdminWorker(user, password, geoserver_url)
        self._gs_rest_worker.login_success.connect(self._on_gs_rest_ok)
        self._gs_rest_worker.login_failed.connect(self._on_gs_rest_fail)
        self._gs_rest_worker.start()

    def _on_gs_rest_ok(self, session, username):
        plugin = getattr(self._dialog, 'plugin', None)
        if plugin:
            plugin.gs_rest_session = session
            plugin.gs_rest_username = username
        self.gs_rest_configured.emit(True, username)

    def _on_gs_rest_fail(self, msg):
        self.gs_rest_configured.emit(False, msg)

    @pyqtSlot(result='QVariant')
    def get_gs_rest_status(self):
        """Retorna o status das credenciais REST do GeoServer para o JS exibir no painel.
        {'has_rest_creds': bool, 'username': str, 'is_sso': bool}"""
        plugin = getattr(self._dialog, 'plugin', None)
        gs_rest = getattr(plugin, 'gs_rest_session', None)
        gs_user = getattr(plugin, 'gs_rest_username', None)
        sso_session = getattr(plugin, 'api_session', None)
        sso_user = getattr(plugin, 'auth_username', None)
        # é usuário SSO quando: tem sessão api mas a sessão usa BearerTokenAuth
        is_sso = bool(sso_session) and hasattr(getattr(sso_session, 'auth', None), '_provider')
        return {
            'has_rest_creds': bool(gs_rest),
            'username': gs_user or '',
            'is_sso': is_sso,
            'sso_username': sso_user or ''
        }

    @pyqtSlot()
    def list_workspaces(self):
        """RF01 - lista os workspaces do GeoServer em background (QThread, RNF02) e
        emite gs_workspaces_ready(workspaces, error) quando terminar."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_workspaces_ready.emit([], 'Serviço GeoServer não inicializado.')
            return
        if self._worker_busy(self._workspaces_worker):
            return
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsWorkspacesWorker
        self._workspaces_worker = _GsWorkspacesWorker(geoserver_service, config_loader)
        self._workspaces_worker.done.connect(self.gs_workspaces_ready.emit)
        self._workspaces_worker.start()

    @pyqtSlot(str)
    def list_datastores(self, workspace):
        """RF01 - lista os datastores de um workspace do GeoServer em background e
        emite gs_datastores_ready(datastores, error) quando terminar."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_datastores_ready.emit([], 'Serviço GeoServer não inicializado.')
            return
        if self._worker_busy(self._datastores_worker):
            return
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsDatastoresWorker
        self._datastores_worker = _GsDatastoresWorker(geoserver_service, workspace, config_loader)
        self._datastores_worker.done.connect(self.gs_datastores_ready.emit)
        self._datastores_worker.start()

    @pyqtSlot(str, str)
    def list_featuretypes(self, workspace, datastore):
        """Lista as tabelas visíveis nesse datastore (list=all) em background e emite
        gs_featuretypes_ready(nomes, error) - usado pra validar, antes de publicar, se a
        tabela da camada ativa realmente existe ali (ver GeoServerService.list_featuretypes)."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_featuretypes_ready.emit([], 'Serviço GeoServer não inicializado.')
            return
        if self._worker_busy(self._featuretypes_worker):
            return
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsFeatureTypesWorker
        self._featuretypes_worker = _GsFeatureTypesWorker(geoserver_service, workspace, datastore, config_loader)
        self._featuretypes_worker.done.connect(self.gs_featuretypes_ready.emit)
        self._featuretypes_worker.start()

    @pyqtSlot()
    def find_datastore_for_active_layer(self):
        """Botão "Detectar automaticamente": varre todos os workspaces/datastores do
        GeoServer procurando onde a tabela da camada ativa está visível (mais lento que
        os outros métodos - reporta progresso via gs_find_datastore_progress). Emite
        gs_find_datastore_done([{'workspace':..,'datastore':..}, ...], error) ao final."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_find_datastore_done.emit([], 'Serviço GeoServer não inicializado.')
            return

        layer = self._active_layer()
        info = geoserver_service.get_active_layer_publish_info(layer)
        if not info.get('publishable') or not info.get('table'):
            self.gs_find_datastore_done.emit([], info.get('reason') or 'Camada não publicável.')
            return
        if self._worker_busy(self._find_datastore_worker):
            return

        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsFindDatastoreWorker
        self._find_datastore_worker = _GsFindDatastoreWorker(geoserver_service, info['table'], config_loader)
        self._find_datastore_worker.progress.connect(self.gs_find_datastore_progress.emit)
        self._find_datastore_worker.done.connect(self.gs_find_datastore_done.emit)
        self._find_datastore_worker.start()

    def _active_layer(self):
        plugin = getattr(self._dialog, 'plugin', None)
        iface = getattr(plugin, 'iface', None) or getattr(self._dialog, 'iface', None)
        return iface.activeLayer() if iface else None

    # ── Rascunho local (workspace/datastore/nome/título/resumo/palavras-chave) ─────
    # Arquivo PRÓPRIO do GS (geoserver_publish_draft.json) - não usa o rascunho do
    # editor GN (geometadata_form_draft.json) de propósito: workspace/datastore/nome-
    # publicado não são campos do metadado MGB, misturar sujaria o rascunho do GN.
    # Mesmo padrão de ui/geonetwork_bridge.py (_draft_path/_layer_key/_load_all_drafts).

    def _draft_path(self) -> str:
        try:
            from qgis.core import QgsApplication
            base = QgsApplication.qgisSettingsDirPath()
        except Exception:
            base = os.path.expanduser('~')
        return os.path.join(base, 'geoserver_publish_draft.json')

    def _layer_key(self) -> str:
        layer = self._active_layer()
        if not layer:
            return '__no_layer__'
        return layer.source() or layer.id()

    def _load_all_drafts(self) -> dict:
        import json
        path = self._draft_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as exc:
            print(f"GeoMetadata [gs _load_all_drafts]: {exc}")
            return {}

    def _save_all_drafts(self, drafts: dict):
        import json
        with open(self._draft_path(), 'w', encoding='utf-8') as f:
            json.dump(drafts, f, ensure_ascii=False)

    @pyqtSlot(str)
    def save_draft(self, json_str: str):
        """Persiste o rascunho do formulário de publicação sob a chave da camada ativa."""
        import json
        try:
            data = json.loads(json_str)
            drafts = self._load_all_drafts()
            drafts[self._layer_key()] = data
            self._save_all_drafts(drafts)
        except Exception as exc:
            print(f"GeoMetadata [gs save_draft]: {exc}")

    @pyqtSlot(result='QVariant')
    def load_draft(self):
        """Retorna o rascunho de publicação da camada ativa, se existir."""
        return self._load_all_drafts().get(self._layer_key())

    @pyqtSlot()
    def clear_draft(self):
        """Remove só o rascunho da camada ativa - não mexe nos drafts de outras camadas."""
        try:
            drafts = self._load_all_drafts()
            if drafts.pop(self._layer_key(), None) is not None:
                self._save_all_drafts(drafts)
        except Exception as exc:
            print(f"GeoMetadata [gs clear_draft]: {exc}")

    def _resolve_uuid_hint_and_draft(self, layer):
        """Parte RÁPIDA (arquivo local, API do QGIS) do que antes era _load_layer_metadata -
        roda na main thread ANTES de disparar _GsActiveLayerInfoWorker (banco/GeoNetwork,
        em background). Retorna (draft, uuid_hint_efetivo) - o hint já embute o uuid do
        rascunho, na mesma prioridade de antes (banco > rascunho > hint recebido do JS,
        ver _merge_layer_metadata/_on_layer_info_ready)."""
        gn_bridge = getattr(self._dialog, 'gn_bridge', None)
        draft = None
        if gn_bridge and layer:
            try:
                layer_key = layer.source() or layer.id()
                draft = gn_bridge._load_all_drafts().get(layer_key)
            except Exception as exc:
                print(f"GeoMetadata [get_active_layer_publish_info] draft: {exc}")
        return draft

    @staticmethod
    def _build_metadata_link_url(uuid, config_loader_instance):
        """Fórmula única da URL do "Link de metadados" (REST featureType, ver
        register_postgis_featuretype) - usada tanto na publicação de verdade
        (_resolve_metadata_link_url) quanto na prévia só-consulta mostrada na aba
        Identificação (info.metadata_link_url, ver _on_layer_info_ready) - as duas
        precisam concordar, senão a prévia mente sobre o que vai ser publicado."""
        if not uuid:
            return ''
        records_url = (config_loader_instance.get_geonetwork_url() or {}).get('records_url')
        if not records_url:
            return ''
        return f"{records_url}/{uuid}/formatters/xml"

    def _resolve_metadata_link_url(self, layer, config_loader_instance):
        """Monta a URL do "Link de metadados" (REST featureType, ver
        register_postgis_featuretype) pro registro MGB dessa camada no GeoNetwork - só
        quando existe um metadata_uuid de verdade SALVO (banco/sidecar via
        persistence_service), nunca um rascunho não publicado (linkaria pra um registro
        que ainda não existe no catálogo, quebrando o link). Roda na main thread (chamada
        de publish_layer, uma ação explícita do usuário - custo aceitável, diferente do
        antigo problema de get_active_layer_publish_info rodando isso a cada troca de
        camada, já corrigido - ver _GsActiveLayerInfoWorker)."""
        # Prints de diagnóstico temporários (não é logging permanente do projeto) - o
        # usuário confirmou que a camada testada JÁ tem metadado no GeoNetwork, mas o link
        # saiu vazio na publicação; sem saber em qual dos 4 pontos isso falha, qualquer
        # tentativa de correção seria chute (mesmo erro que já custou caro com o SRS/[GS-500]).
        try:
            ps = getattr(self._dialog, 'persistence_service', None)
            if not ps or not layer:
                print(f"GeoMetadata [metadata link] abortado: persistence_service={ps!r} layer={layer!r}")
                return None
            xml_content = ps.load(layer)
            if not xml_content:
                print("GeoMetadata [metadata link] abortado: ps.load(layer) não retornou XML nenhum (nada salvo pra essa camada no banco/sidecar)")
                return None
            from ..core import xml_parser
            saved = xml_parser.parse_xml_to_dict(xml_content, is_string=True) or {}
            uuid = saved.get('metadata_uuid')
            if not uuid:
                print(f"GeoMetadata [metadata link] abortado: XML salvo achado, mas sem metadata_uuid. Chaves presentes: {list(saved.keys())}")
                return None
            url = self._build_metadata_link_url(uuid, config_loader_instance)
            if not url:
                print(f"GeoMetadata [metadata link] abortado: get_geonetwork_url() não tem 'records_url' - {config_loader_instance.get_geonetwork_url()!r}")
                return None
            print(f"GeoMetadata [metadata link] OK - uuid={uuid} url={url}")
            return url
        except Exception as exc:
            print(f"GeoMetadata [metadata link] EXCEÇÃO: {exc}")
            return None

    @staticmethod
    def _merge_layer_metadata(draft, local_metadata, gn_remote):
        """Mesma prioridade de preenchimento que _load_layer_metadata tinha: 1) GeoNetwork
        online (mais confiável, reflete o que está de fato publicado) 2) banco/sidecar
        local (PersistenceService, via fetch_saved_records) 3) rascunho do editor GN
        (arquivo local, só como último recurso - não deve pisar em cima de um metadado que
        já existe de verdade online ou no banco)."""
        if gn_remote:
            return gn_remote
        if local_metadata and (local_metadata.get('title') or local_metadata.get('abstract') or local_metadata.get('MD_Keywords')):
            return local_metadata
        if draft and (draft.get('title') or draft.get('abstract') or draft.get('MD_Keywords')):
            return draft
        return local_metadata or draft or {}

    @pyqtSlot(str)
    def get_active_layer_publish_info(self, gn_uuid_hint=''):
        """Diz ao JS (via sinal gs_layer_info_ready, não retorno direto - ver abaixo) se a
        camada ativa do QGIS pode ser publicada no GeoServer (RF02) - só camadas PostGIS
        são suportadas, ver GeoServerService.get_active_layer_publish_info. Quando
        publicável, inclui 'title'/'abstract'/'keywords' pré-preenchidos a partir do
        metadado MGB salvo (se existir) e 'saved_workspace'/'saved_datastore'/
        'saved_published_name'/'saved_title'/'saved_abstract'/'saved_keywords'/
        'saved_published'/'saved_style_*' - o destino usado na última publicação/
        salvamento de verdade dessa camada (geoserver_publish_xml). Prioridade de
        preenchimento no JS: banco (isso aqui) > rascunho local (load_draft), estando
        logado ou não - o rascunho só preenche o que o banco deixou vazio.

        Roda em background (QThread, RNF02 - ver _GsActiveLayerInfoWorker) e emite
        gs_layer_info_ready(info) quando terminar, em vez de retornar direto: a busca (até
        duas conexões psycopg2 + potencialmente uma chamada REST ao GeoNetwork) era toda
        síncrona aqui antes, travando a UI inteira (Qt event loop, inclusive o compositor
        da QWebEngineView) toda vez que o painel GS abria ou a camada ativa mudava, sem
        short-circuit nenhum (diferente do editor GN, que só cai pro banco quando não há
        rascunho local - ver geonetwork_bridge.load_draft). Só a parte que toca API do
        QGIS (camada ativa, layer.source(), auth manager, rascunho local) roda aqui, na
        main thread - o resto (rede) vai pro worker."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_layer_info_ready.emit({'publishable': False, 'reason': 'Serviço GeoServer não inicializado.'})
            return
        try:
            layer = self._active_layer()
            info = geoserver_service.get_active_layer_publish_info(layer)
            if not info.get('publishable'):
                self.gs_layer_info_ready.emit(info)
                return

            draft = self._resolve_uuid_hint_and_draft(layer)
            effective_hint = (draft or {}).get('metadata_uuid') or gn_uuid_hint or None

            from ..core.geoserver_service import resolve_layer_db_params
            conn_params, details = resolve_layer_db_params(layer)
            from ..core.plugin_config import config_loader
            from .geoserver_workers import _GsActiveLayerInfoWorker
            geonetwork_service = getattr(self._dialog, 'geonetwork_service', None)

            worker = _GsActiveLayerInfoWorker(
                conn_params, details.get('f_table_catalog'), details.get('f_table_schema'), details.get('f_table_name'),
                effective_hint, geonetwork_service, config_loader
            )
            worker._ctx_base_info = info
            worker._ctx_draft = draft
            self._layer_info_workers.append(worker)
            worker.done.connect(self._on_standard_layer_info_ready)
            worker.start()
        except Exception as exc:
            self.gs_layer_info_ready.emit({'publishable': False, 'reason': str(exc)})

    @pyqtSlot('QVariant')
    def _on_standard_layer_info_ready(self, result):
        worker = self.sender()
        if worker in self._layer_info_workers:
            self._layer_info_workers.remove(worker)
        self._on_layer_info_ready(result, worker, getattr(worker, '_ctx_base_info', {}), getattr(worker, '_ctx_draft', None))

    def _on_layer_info_ready(self, result, worker, base_info, draft):
        """Handler do _GsActiveLayerInfoWorker.done (ver get_active_layer_publish_info) -
        junta o que veio do worker (banco + GeoNetwork) com o `info` base (já calculado na
        main thread) e finalmente emite gs_layer_info_ready pro JS."""
        if worker in self._layer_info_workers:
            self._layer_info_workers.remove(worker)
        info = dict(base_info)
        md = self._merge_layer_metadata(draft, result.get('local_metadata'), result.get('gn_remote'))
        info['title'] = md.get('title') or info.get('name') or ''
        info['abstract'] = md.get('abstract') or ''
        info['keywords'] = md.get('MD_Keywords') or []
        # Prévia só-consulta (aba Identificação, ver geoserver.js) do que
        # register_postgis_featuretype vai de fato usar como "Link de metadados" na
        # publicação (_resolve_metadata_link_url) - mesmo uuid já resolvido acima (banco/
        # rascunho/GeoNetwork), sem bater no banco de novo. Vazio quando a camada ainda não
        # tem metadado nenhum salvo - nesse caso a publicação também não vai criar o link.
        metadata_uuid = md.get('metadata_uuid') or ''
        info['metadata_uuid'] = metadata_uuid
        if metadata_uuid:
            from ..core.plugin_config import config_loader
            info['metadata_link_url'] = self._build_metadata_link_url(metadata_uuid, config_loader)
        else:
            info['metadata_link_url'] = ''

        saved = result.get('saved_destination') or {}
        info['saved_workspace'] = saved.get('workspace') or ''
        info['saved_datastore'] = saved.get('datastore') or ''
        info['saved_published_name'] = saved.get('published_name') or ''
        info['saved_title'] = saved.get('title') or ''
        info['saved_abstract'] = saved.get('abstract') or ''
        info['saved_keywords'] = saved.get('keywords') or []
        info['saved_published'] = bool(saved.get('published'))
        info['saved_style_source'] = saved.get('style_source') or ''
        info['saved_style_name'] = saved.get('style_name') or ''
        info['saved_style_workspace'] = saved.get('style_workspace') or ''
        # Faltava esse campo aqui (bug pré-existente, não introduzido nessa refatoração) -
        # _build_publish_xml grava style_additional_json certinho (ver save_publish_destination),
        # mas esse método nunca devolvia ele pro JS. _renderGsLayerCard (geoserver.js) só
        # restaura _gsAdditionalStyles quando 'info.saved_style_additional_json' existe -
        # sem isso, toda revisita/reabertura numa camada com estilos adicionais perdia
        # essa lista, e a checagem ao vivo (check_gs_sync) comparava "nada local" contra
        # os adicionais que estão de fato no GeoServer -> "Modificado" pra sempre.
        info['saved_style_additional_json'] = saved.get('style_additional_json') or ''
        # Banco inacessível agora (ver _GsActiveLayerInfoWorker/fetch_saved_records) -
        # 'saved_*' acima ficam todos vazios como se a camada nunca tivesse sido salva; sem
        # esse flag o JS (_renderGsLayerCard, geoserver.js) mostraria "Não Encontrado"
        # silenciosamente, escondendo que a causa foi só conectividade.
        info['db_error'] = bool(result.get('db_error'))
        if info['db_error']:
            self._notify_db_offline()
        self.gs_layer_info_ready.emit(info)

    @pyqtSlot(str, result=str)
    def sanitize_layer_name(self, name):
        """RF04 - preview síncrono do nome sanitizado (só regex, sem I/O de rede)."""
        from ..core.geoserver_service import GeoServerService
        return GeoServerService.sanitize_layer_name(name)

    # ── Estilos (SLD) ───────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def list_styles(self, workspace):
        """Lista os estilos disponíveis (globais + do workspace) em background e emite
        gs_styles_ready(styles, error) - popula o select "Usar estilo existente" da aba
        Estilos (ver GeoServerService.list_styles)."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_styles_ready.emit([], 'Serviço GeoServer não inicializado.')
            return
        if self._worker_busy(self._styles_worker):
            return
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsStylesWorker
        self._styles_worker = _GsStylesWorker(geoserver_service, workspace, config_loader)
        self._styles_worker.done.connect(self.gs_styles_ready.emit)
        self._styles_worker.start()

    @pyqtSlot(result='QVariant')
    def pick_sld_file(self):
        """Abre o QFileDialog nativo pro usuário escolher um arquivo .sld (aba Estilos,
        fonte "arquivo"). Validação leve na hora (existe + parece um SLD), pro usuário
        saber imediatamente se escolheu o arquivo errado - o conteúdo é relido na
        publicação (_read_sld_file), não guardado aqui."""
        from qgis.PyQt.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self._dialog, 'Escolher arquivo SLD', '', 'Estilos SLD (*.sld *.xml);;Todos os arquivos (*.*)'
        )
        if not path:
            return {'ok': False, 'cancelled': True}
        body, error = self._read_sld_file(path)
        if error:
            return {'ok': False, 'error': error}
        return {'ok': True, 'path': path, 'filename': os.path.basename(path)}

    @staticmethod
    def _read_sld_file(path):
        """Lê e valida (superficialmente) um arquivo SLD. Retorna (body, error)."""
        if not path or not os.path.exists(path):
            return None, 'Arquivo SLD não encontrado: ' + (path or '(vazio)')
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                body = f.read()
        except Exception as exc:
            return None, f'Não foi possível ler o arquivo SLD: {exc}'
        if 'StyledLayerDescriptor' not in body:
            return None, 'O arquivo escolhido não parece ser um SLD válido (sem <StyledLayerDescriptor>).'
        return body, ''

    def _export_active_layer_sld(self, layer):
        """Exporta a simbologia ATUAL da camada no QGIS como SLD (saveSldStyle). Precisa
        rodar na UI thread (API do QGIS não é thread-safe) - por isso o bridge gera o
        corpo AQUI, antes de despachar o worker, e o worker só faz o tráfego REST.
        Retorna (body, error)."""
        if not layer or not hasattr(layer, 'saveSldStyle'):
            return None, 'A camada ativa não suporta exportação de estilo SLD.'
        import tempfile
        tmp_path = os.path.join(tempfile.gettempdir(), 'geometadata_sld_export.sld')
        try:
            result = layer.saveSldStyle(tmp_path)
            # PyQGIS devolve (mensagem, ok) na maioria das versões; algumas só a mensagem.
            ok = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else True
            message = result[0] if isinstance(result, (tuple, list)) else str(result or '')
            if not ok:
                return None, 'O QGIS não conseguiu exportar o estilo desta camada como SLD: ' + (message or 'erro desconhecido.')
            return self._read_sld_file(tmp_path)
        except Exception as exc:
            return None, f'Erro ao exportar o estilo da camada como SLD: {exc}'
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def _prepare_style_task(self, style_cfg, layer, workspace):
        """Transforma a configuração da aba Estilos (JS) na tarefa que os workers executam
        (GeoServerService.apply_style). Roda na UI thread de propósito: a exportação do
        SLD do QGIS (fonte 'qgis') usa a API do QGIS, e a leitura do arquivo (fonte
        'file') é local/rápida - só o tráfego REST vai pro worker. `style_cfg` vem do JS:
        {'source': ''|'qgis'|'file'|'existing', 'name':, 'file_path':, 'existing_name':,
        'existing_workspace':, 'additional': [...]}. Retorna (task|None, error)."""
        from ..core.geoserver_service import GeoServerService

        def _prep_entry(cfg, is_default=False):
            source = (cfg or {}).get('source') or ''
            if not source or source == 'none':
                return None, ''
            if source == 'existing':
                name = (cfg.get('existing_name') or '').strip()
                if not name:
                    return None, 'Escolha um estilo existente na aba Estilos antes de continuar.'
                return {
                    'mode': 'existing',
                    'name': name,
                    'style_workspace': (cfg.get('existing_workspace') or '').strip(),
                    'sld_body': '',
                }, ''
            name = GeoServerService.sanitize_layer_name(cfg.get('name') or '')
            if not name:
                return None, 'Informe o nome do estilo na aba Estilos antes de continuar.'
            if source == 'qgis':
                if not is_default:
                    return None, 'A fonte "qgis" (Estilo atual do QGIS) só pode ser usada no estilo padrão, não como adicional.'
                body, error = self._export_active_layer_sld(layer)
            elif source == 'file':
                body, error = self._read_sld_file(cfg.get('file_path') or '')
            else:
                return None, f'Fonte de estilo desconhecida: {source}'
            if error:
                return None, error
            return {'mode': 'create', 'name': name, 'style_workspace': workspace, 'sld_body': body}, ''

        default_entry, def_err = _prep_entry(style_cfg, is_default=True)
        if def_err:
            return None, def_err

        additional_entries = []
        for a_cfg in (style_cfg.get('additional') or []):
            a_entry, a_err = _prep_entry(a_cfg, is_default=False)
            if a_err:
                return None, f"Erro no estilo adicional '{a_cfg.get('name') or a_cfg.get('existing_name')}': {a_err}"
            if a_entry:
                additional_entries.append(a_entry)

        if not default_entry and not additional_entries:
            return None, ''

        return {'default': default_entry, 'additional': additional_entries}, ''

    @staticmethod
    def derive_style_fields(style_cfg, workspace):
        """Reduz a configuração da aba Estilos aos campos persistidos em geoserver_publish_xml
        (style_source/name/workspace e style_additional_json). Retorna a tupla
        (source, name, workspace, additional_json)."""
        import json
        from ..core.geoserver_service import GeoServerService

        def _extract(cfg):
            src = (cfg or {}).get('source') or ''
            if src == 'none': src = ''
            nm = ws = ''
            if src == 'existing':
                nm = (cfg.get('existing_name') or '').strip()
                ws = (cfg.get('existing_workspace') or '').strip()
            elif src:
                nm = GeoServerService.sanitize_layer_name(cfg.get('name') or '')
                ws = workspace or ''
            if not nm:
                return '', '', ''
            return src, nm, ws

        d_src, d_nm, d_ws = _extract(style_cfg)
        
        adds = []
        for a_cfg in (style_cfg.get('additional') or []):
            a_src, a_nm, a_ws = _extract(a_cfg)
            if a_nm:
                # Na persistência JSON guardamos os campos do cfg pra UI conseguir reconstruir fácil
                # (igual no snapshot)
                adds.append(a_cfg)
        adds_json = json.dumps(adds) if adds else ''

        return d_src, d_nm, d_ws, adds_json

    @pyqtSlot(str, str, str)
    def pull_layer_from_server(self, workspace, datastore, published_name):
        """"Serviços > Baixar Camada" (banner "Atualização disponível", como o GN) -
        PULL, não push: busca o que está DE FATO publicado no GeoServer agora (título/
        resumo/palavras-chave + estilo padrão/adicionais, só leitura - ver
        _GsPullLayerWorker) e devolve pro JS aplicar no formulário local, sobrescrevendo o
        que estava digitado. Complementa "Publicar Camada" (cria OU atualiza, push
        deliberado do que está no formulário) - esse aqui existe pro caso oposto:
        quando o formulário/banco LOCAL está desatualizado em relação ao que foi
        publicado de verdade (ex.: outro técnico publicou por cima depois que você só
        salvou um destino no banco) - empurrar o local sobrescreveria o trabalho de quem
        publicou por último, então a direção certa é trazer o servidor pra cá. Emite
        gs_layer_pulled(ok, dados, error); em caso de sucesso, grava os dados PUXADOS em
        geoserver_publish_xml (a fonte de verdade agora é o que o servidor tinha), pra um
        técnico em outra máquina recuperar o estado correto via banco."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service or not workspace or not datastore or not published_name:
            self.gs_layer_pulled.emit(False, {}, '[UI-004] Destino de publicação incompleto (workspace/datastore/nome).')
            return
        if self._worker_busy(self._pull_layer_worker) or self._worker_busy(self._pull_by_wms_worker):
            return
        layer = self._active_layer()
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsPullLayerWorker
        self._pull_layer_worker = _GsPullLayerWorker(
            geoserver_service, workspace, datastore, published_name, config_loader
        )
        # Salva o contexto no próprio worker para evitar uso de lambda (que causa crash
        # no QWebChannel por executar em DirectConnection na thread de background)
        self._pull_layer_worker._ctx_layer = layer
        self._pull_layer_worker._ctx_workspace = workspace
        self._pull_layer_worker._ctx_datastore = datastore
        self._pull_layer_worker._ctx_published_name = published_name
        
        self._pull_layer_worker.done.connect(self._on_standard_layer_pulled)
        self._pull_layer_worker.start()

    @pyqtSlot(bool, 'QVariant', str)
    def _on_standard_layer_pulled(self, ok, data, error):
        """Handler seguro (QueuedConnection via @pyqtSlot) para pull_layer_from_server.
        Evita o crash do QGIS ao emitir sinais JS a partir de background threads."""
        worker = self.sender()
        self._on_layer_pulled(
            ok, data, error,
            getattr(worker, '_ctx_layer', None),
            getattr(worker, '_ctx_workspace', ''),
            getattr(worker, '_ctx_datastore', ''),
            getattr(worker, '_ctx_published_name', '')
        )


    def _on_layer_pulled(self, ok, data, error, layer, workspace, datastore, published_name):
        """Persiste no banco o que acabou de vir do GeoServer (título/resumo/palavras-
        chave/estilo) - a partir de agora ESSE é o estado correto/salvo, não mais o que
        estava só no formulário local (ver pull_layer_from_server acima)."""
        if ok and layer:
            geoserver_service = getattr(self._dialog, 'geoserver_service', None)
            if geoserver_service:
                import json
                additional_styles = data.get('additional_styles') or []
                adds = [
                    {'source': 'existing', 'existing_name': a.get('name') or '', 'existing_workspace': a.get('style_workspace') or ''}
                    for a in additional_styles if a.get('name')
                ]
                default_style = data.get('default_style') or ''
                geoserver_service.save_publish_destination(
                    layer, workspace, datastore, published_name,
                    data.get('title') or published_name, data.get('abstract') or '', data.get('keywords') or [],
                    published=True,
                    style_source='existing' if default_style else '',
                    style_name=default_style,
                    style_workspace=data.get('default_style_workspace') or '',
                    style_additional_json=json.dumps(adds) if adds else ''
                )
        self.gs_layer_pulled.emit(ok, data or {}, error or '')

    @pyqtSlot(str)
    def pull_gs_layer_by_wms_name(self, ws_layer_name: str):
        """"Serviços > Baixar Camada" quando não há camada PostGIS ativa no QGIS mas o
        usuário já fez pull do GeoNetwork e o metadado tem um link WMS/WFS com o nome da
        camada publicada no formato 'workspace:published_name' (CI_OnlineResource name,
        campo geoserver_layer_name de wms_data — xml_parser.py).

        Difere de pull_layer_from_server (que exige layer ativo + workspace/datastore/nome
        já preenchidos pelo usuário) em dois pontos:
        - Descobre o datastore automaticamente (find_datastore_for_published_name), sem exigir
          camada PostGIS ativa ou que o usuário saiba/tenha preenchido o destino.
        - Não persiste no banco (layer=None para _on_layer_pulled): sem camada ativa não há
          chave de persistência. O formulário GS é atualizado na tela, mas o save fica como
          rascunho local (save_gs_draft_now chamado pelo JS no handler gs_layer_pulled).

        Emite gs_layer_pulled(ok, data, error) — mesmo sinal de pull_layer_from_server,
        reutilizando integralmente o handler JS gs_layer_pulled.connect (geoserver.js)."""
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service or not ws_layer_name:
            self.gs_layer_pulled.emit(
                False, {},
                '[UI-005] Sem serviço GeoServer ou nome de camada WMS/WFS inválido.'
            )
            return
        if self._worker_busy(self._pull_layer_worker) or self._worker_busy(self._pull_by_wms_worker):
            return
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsPullLayerByWmsNameWorker
        self._pull_by_wms_worker = _GsPullLayerByWmsNameWorker(
            geoserver_service, ws_layer_name, config_loader
        )
        self._pull_by_wms_worker.done.connect(self._on_wms_layer_pulled)
        self._pull_by_wms_worker.start()

    @pyqtSlot(bool, 'QVariant', str)
    def _on_wms_layer_pulled(self, ok, data, error):
        """Handler seguro (QueuedConnection garantida pelo PyQt via @pyqtSlot) para o
        resultado do _GsPullLayerByWmsNameWorker. Evita o crash do QWebChannel que ocorria
        ao usar um lambda, o qual executava _on_layer_pulled direto na thread do worker."""
        self._on_layer_pulled(ok, data, error, None, '', '', '')



    @pyqtSlot(str, str, str, str, str, 'QVariant', str)
    def check_gs_sync(self, workspace, datastore, published_name, title, abstract, keywords, style_json=''):
        """Compara o formulário atual contra o que está DE FATO publicado no GeoServer
        agora (REST, ao vivo via GeoServerService.fetch_published_featuretype) - nível
        'sistema' do badge combinado/painel GS (mesmo espírito de check_gn_sync, ver
        já existe destino conhecido (workspace/datastore/nome) - o nível 'banco' (sem
        esse live-check) continua resolvido inteiramente no JS via info.saved_* (ver
        get_active_layer_publish_info), sem depender deste método.

        Roda em background (QThread, RNF02 - ver _GsSyncCheckWorker) e emite
        gs_sync_checked(result) quando terminar, em vez de retornar direto: a chamada de
        rede aqui é síncrona (requests.get) e travava o painel GS inteiro (UI thread
        bloqueada) enquanto esperava a resposta do GeoServer, na primeira versão deste
        método. `result` é um dict {'state': 'sys_synced'|'sys_modified'|'sys_not_found'|
        'error', 'workspace':, 'datastore':, 'published_name':, [+ 'title'/'abstract'/
        'keywords' ao vivo quando encontrado]} - o JS usa workspace/datastore/
        published_name pra confirmar que a resposta ainda corresponde à checagem que ele
        espera (ver _onGsSyncChecked, geoserver.js). `style_json` é a configuração da aba
        Estilos (mesmo formato de _prepare_style_task/derive_style_fields) - repassada pro
        worker pra ele comparar o estilo padrão/adicionais contra o que está de fato
        aplicado na camada (fetch_layer_styles)."""
        import json
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service or not workspace or not datastore or not published_name:
            # workspace/datastore/published_name inclusos mesmo no erro - o JS usa esses três
            # campos pra casar a resposta com a checagem que esperava (_onGsSyncChecked,
            # geoserver.js); sem eles a resposta parecia "de outra camada" e era descartada
            # em silêncio, deixando o badge preso em "verificando" pra sempre.
            self.gs_sync_checked.emit({
                'state': 'error', 'workspace': workspace, 'datastore': datastore, 'published_name': published_name
            })
            return
        try:
            style_cfg = json.loads(style_json) if style_json else {}
        except ValueError:
            style_cfg = {}
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsSyncCheckWorker
        keywords = list(keywords) if keywords else []
        worker = _GsSyncCheckWorker(
            geoserver_service, workspace, datastore, published_name, title, abstract, keywords, config_loader, style_cfg
        )
        self._sync_check_workers.append(worker)
        worker.done.connect(self.gs_sync_checked.emit)
        worker.done.connect(lambda _r, w=worker: self._sync_check_workers.remove(w) if w in self._sync_check_workers else None)
        worker.start()

    @pyqtSlot(str, str, str, str, str, 'QVariant', str)
    def save_destination_now(self, workspace, datastore, published_name, title, abstract, keywords, style_json=''):
        """"Continuar Depois" do painel GeoServer: grava o destino atual (workspace/
        datastore/nome/título/resumo/palavras-chave/estilo) em geoserver_publish_xml SEM
        publicar de verdade no GeoServer - complementa o rascunho local (por máquina, só
        esse QGIS) com uma cópia durável no banco, sem depender do usuário ter passado pelo
        "Continuar Depois" do editor GN pra essa mesma promoção acontecer (ver
        GeoMetadata_dialog._promote_gs_draft_to_db, que já faz isso automaticamente - esse
        slot é o atalho explícito direto do painel GeoServer). O estilo aqui é só a ESCOLHA
        (fonte + nome) - nada é exportado/enviado ao GeoServer, igual aos outros campos.
        Emite gs_destination_saved(db_ok) pro JS avisar o usuário do resultado."""
        import json
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        layer = self._active_layer()
        if not geoserver_service or not layer:
            self.gs_destination_saved.emit(False)
            return
        keywords = list(keywords) if keywords else []
        try:
            style_cfg = json.loads(style_json) if style_json else {}
        except ValueError:
            style_cfg = {}
        style_source, style_name, style_workspace, style_additional_json = self.derive_style_fields(style_cfg, workspace)
        ok = geoserver_service.save_publish_destination(
            layer, workspace, datastore, published_name, title, abstract, keywords,
            style_source=style_source, style_name=style_name, style_workspace=style_workspace,
            style_additional_json=style_additional_json
        )
        self.gs_destination_saved.emit(ok)

    @pyqtSlot(str, str, str, str, str, 'QVariant', str)
    def publish_layer(self, workspace, datastore, published_name, title, abstract, keywords, style_json=''):
        """RF02 - publica (registra) a camada ativa do QGIS como FeatureType no
        workspace/datastore escolhidos, OU atualiza se esse destino já está publicado -
        mesma filosofia do "Publicar Metadados" do GN (uma ação só, cria ou atualiza, o
        backend decide sozinho) - antes, tentar publicar de novo numa camada já publicada
        sempre falhava com [GS-409] "Já existe uma camada com esse nome"; a única forma de
        corrigir SÓ o estilo era um botão à parte ("Serviços > Atualizar Estilo", removido -
        ver docs_projeto/bugs.md). Reconsulta a camada ativa aqui (não confia em estado
        antigo vindo do JS) e dispara o worker em background (RNF02). title/abstract/
        keywords vêm explicitamente do JS (o mesmo valor que get_active_layer_publish_info
        já tinha calculado e mostrado na tela) - 'name'/'nativeName' seguem a regra de
        sanitização (RF04), os demais são livres. `style_json` é a configuração da aba
        Estilos (ver _prepare_style_task) - o preparo (exportar SLD do QGIS/ler arquivo)
        acontece AQUI, na UI thread, e o worker só faz o tráfego REST."""
        import json
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_publish_done.emit(False, '[SYS-001] Serviço GeoServer não inicializado.', published_name, '', '')
            return
        if self._worker_busy(self._publish_worker):
            return

        layer = self._active_layer()
        info = geoserver_service.get_active_layer_publish_info(layer)
        if not info.get('publishable'):
            self.gs_publish_done.emit(False, info.get('reason') or '[UI-004] Camada não publicável.', published_name, '', '')
            return

        # CRS que o QGIS já conhece da própria camada (ex.: 'EPSG:4674') - tem que ser lido
        # aqui, na main thread (layer.crs() é API do QGIS) - ver register_postgis_featuretype
        # sobre por que isso importa (SRS Nativo ficava vazio na UI do GeoServer sem isso).
        try:
            srs = layer.crs().authid() or None
        except Exception:
            srs = None

        keywords = list(keywords) if keywords else []

        try:
            style_cfg = json.loads(style_json) if style_json else {}
        except ValueError:
            style_cfg = {}
        style_task, style_error = self._prepare_style_task(style_cfg, layer, workspace)
        if style_error:
            # Erro de PREPARO do estilo (arquivo sumiu, export do QGIS falhou) - barra a
            # publicação antes de qualquer tráfego: o usuário pediu explicitamente um
            # estilo, publicar sem ele e avisar depois seria pior que deixar corrigir já.
            self.gs_publish_done.emit(False, style_error, published_name, '', '')
            return

        from ..core.plugin_config import config_loader
        publish_title = title or published_name
        metadata_link_url = self._resolve_metadata_link_url(layer, config_loader)

        # Detecta CRIAR vs ATUALIZAR antes de disparar o worker - uma chamada de leitura a
        # mais (já usada pelo badge/pull, GET simples), mas evita SEMPRE bater com [GS-409]
        # numa camada já publicada. Falha nessa checagem (rede/sessão) não impede tentar
        # criar do jeito de sempre - se REALMENTE já existir, o [GS-409] de sempre cobre.
        already_published = None
        try:
            already_published = geoserver_service.fetch_published_featuretype(workspace, datastore, published_name, config_loader)
        except Exception as exc:
            print(f"GeoMetadata [publish_layer] checagem de existência falhou, seguindo com criação: {exc}")

        if already_published is not None:
            from .geoserver_workers import _GsUpdateMetadataWorker
            self._publish_worker = _GsUpdateMetadataWorker(
                geoserver_service, workspace, datastore, published_name, publish_title, abstract, keywords,
                style_task, config_loader, metadata_link_url
            )
            self._publish_worker.done.connect(
                lambda success, message: self._on_publish_done(
                    success, message, published_name, workspace, datastore, publish_title, abstract, keywords, layer, config_loader,
                    style_cfg.get('source') or '', style_task
                )
            )
            self._publish_worker.start()
            return

        from .geoserver_workers import _GsPublishWorker
        self._publish_worker = _GsPublishWorker(
            geoserver_service, workspace, datastore, info['table'], published_name,
            publish_title, abstract, keywords, config_loader, style_task, srs=srs,
            metadata_link_url=metadata_link_url
        )
        self._publish_worker.done.connect(
            lambda success, message, name: self._on_publish_done(
                success, message, name, workspace, datastore, publish_title, abstract, keywords, layer, config_loader,
                style_cfg.get('source') or '', style_task
            )
        )
        self._publish_worker.start()

    def _on_publish_done(self, success, message, published_name, workspace, datastore, title, abstract, keywords, layer, config_loader_instance,
                         style_source='', style_task=None):
        """Além de repassar o resultado, calcula as URLs WMS/WFS da camada recém-publicada -
        usadas pelo JS (geonetwork.js) pra vincular automaticamente os dois em Distribuição
        e gerar a miniatura, sem o usuário ter que ir lá manualmente linkar de novo. Também
        grava o destino usado (workspace/datastore/nome/título/resumo/palavras-chave/estilo)
        em geoserver_publish_xml (public.qgis_geometadata_plugin), pra pré-preencher a
        próxima vez mesmo sem rascunho local (ver GeoServerService.save_publish_destination).
        Com sucesso mas `message` preenchida (aviso: o estilo falhou, ver _GsPublishWorker/
        _GsUpdateMetadataWorker), os campos de estilo ficam de FORA da gravação - o badge
        segue acusando a pendência e o usuário pode tentar de novo publicando/atualizando
        outra vez (a mesma ação "Publicar Camada" cobre os dois casos, ver publish_layer)."""
        wms_url = wfs_url = ''
        if success:
            base_url = config_loader_instance.get_geoserver_url().rstrip('/')
            wms_url = f"{base_url}/{workspace}/wms?service=WMS"
            wfs_url = f"{base_url}/{workspace}/wfs?service=WFS"
            geoserver_service = getattr(self._dialog, 'geoserver_service', None)
            if geoserver_service:
                style_ok = bool(style_task) and not message
                
                adds = []
                if style_ok and style_task:
                    adds_entries = style_task.get('additional') or []
                    import json
                    # Extraímos só source/name/workspace pra salvar json no banco,
                    # recriando o formato da UI
                    adds = [{'source': 'existing' if e.get('mode') == 'existing' else 'create',
                             'existing_name': e['name'], 'existing_workspace': e.get('style_workspace','')} 
                            if e.get('mode') == 'existing' 
                            else {'source': 'file', 'name': e['name']} 
                            for e in adds_entries]
                
                geoserver_service.save_publish_destination(
                    layer, workspace, datastore, published_name, title, abstract, keywords, published=True,
                    style_source=style_source if style_ok else '',
                    style_name=(style_task.get('default', {}).get('name') if style_task and style_task.get('default') else '') if style_ok else '',
                    style_workspace=(style_task.get('default', {}).get('style_workspace') if style_task and style_task.get('default') else '') if style_ok else '',
                    style_additional_json=json.dumps(adds) if adds else ''
                )
        self.gs_publish_done.emit(success, message, published_name, wms_url, wfs_url)

    @pyqtSlot(str)
    def search_geoserver(self, query: str):
        """Busca camadas no GeoServer via WMS GetCapabilities. Usado pelo editor GN (aba
        'Recursos associados', linkar WMS/WFS - funciona sem login, catálogo público) e
        pela busca de camadas do painel GS (openGsSearchModal, geoserver.js - "Baixar
        Camada" sem depender de camada QGIS ativa nem de um pull do GN antes - essa exige
        login antes de abrir, ver pullGsLayerFromServer).

        Fire-and-forget (RNF02) - resultado chega por gs_search_ready(camadas, erro). Antes
        rodava direto neste pyqtSlot (bloqueante, `result='QVariant'`) - GetCapabilities é
        rede, podia demorar vários segundos dependendo do tamanho do catálogo, travando a
        QWebEngineView inteira: tanto ao abrir a busca quanto a CADA LETRA digitada
        enquanto a 1ª busca da sessão ainda estava em voo (cada tecla reabria outra busca
        síncrona por cima, empilhando o travamento). Cache module-level
        (_geoserver_layers_cache) evita rede de novo em buscas seguintes - essas continuam
        síncronas (só filtram uma lista já em memória, sem I/O), por isso não precisam de
        worker. Nota: o cache não distingue sessão anônima de autenticada - se a 1ª busca da
        sessão do plugin rodar ANTES de logar (ex.: GN "Recursos associados"), fica cacheada
        só com o que a chamada anônima viu (normalmente 1 workspace liberado), e logar
        DEPOIS não refaz a busca - só fechar/reabrir o plugin renova o cache."""
        if GeoServerBridge._geoserver_layers_cache is not None:
            self._emit_gs_search_results(query)
            return
        if self._worker_busy(self._search_layers_worker):
            # Busca anterior (1ª da sessão) ainda em voo - refaz com a query MAIS RECENTE
            # quando ela terminar, em vez de disparar outra busca de rede por cima (o que
            # travava a tela de novo a cada letra digitada nesse meio-tempo).
            self._pending_search_query = query
            return
        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsSearchLayersWorker
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        self._pending_search_query = None
        self._search_layers_worker = _GsSearchLayersWorker(config_loader.get_geoserver_url(), geoserver_service)
        self._search_layers_worker.done.connect(
            lambda layers, err, q=query: self._on_search_layers_done(q, layers, err)
        )
        self._search_layers_worker.start()

    def _on_search_layers_done(self, query, layers, error):
        if error:
            print(f"GeoMetadata [search_geoserver] ERRO: {error}")
            self.gs_search_ready.emit([], error)
            self._pending_search_query = None
            return
        GeoServerBridge._geoserver_layers_cache = layers
        effective_query = self._pending_search_query if self._pending_search_query is not None else query
        self._pending_search_query = None
        self._emit_gs_search_results(effective_query)

    def _emit_gs_search_results(self, query):
        is_logged = getattr(getattr(self._dialog, 'plugin', None), 'api_session', None) is not None
        q = (query or '').lower().strip()
        cache = GeoServerBridge._geoserver_layers_cache or []
        results = [dict(l, wfs_available=is_logged) for l in cache if q in l['name'].lower() or q in l['title'].lower()][:25]
        self.gs_search_ready.emit(results, '')

    @pyqtSlot(str, str, str, str, str, 'QVariant', str, str)
    def update_layer_metadata(self, workspace, datastore, published_name, title, abstract, keywords, style_json='', metadata_uuid=''):
        geoserver_service = getattr(self._dialog, 'geoserver_service', None)
        if not geoserver_service:
            self.gs_metadata_updated.emit(False, 'Serviço GeoServer não inicializado.')
            return
        if self._worker_busy(self._update_metadata_worker):
            return

        style_task = None
        if style_json:
            import json
            try:
                style_cfg = json.loads(style_json)
                if style_cfg.get('source') not in ('', 'none'):
                    # pass None for layer since there's no active layer in this flow
                    style_task, error = self._prepare_style_task(style_cfg, None, workspace)
                    if error:
                        self.gs_metadata_updated.emit(False, error)
                        return
            except Exception as e:
                self.gs_metadata_updated.emit(False, f"Erro ao processar estilo: {e}")
                return

        from ..core.plugin_config import config_loader
        from .geoserver_workers import _GsUpdateMetadataWorker
        # _resolve_metadata_link_url exige um QgsMapLayer (lê o metadata_uuid salvo via
        # persistence_service.load(layer)) - não dá pra usar aqui, esse fluxo roda sem
        # camada ativa (workspace/datastore/published_name vêm de um link WMS/WFS puxado
        # do GN, não de uma camada do QGIS). metadata_uuid chega pronto do JS (o próprio
        # registro que acabou de ser puxado do GN, ver _gnSyncUuid/geonetwork.js) - mesma
        # fórmula de URL (_build_metadata_link_url), só sem precisar resolver via layer.
        metadata_link_url = self._build_metadata_link_url(metadata_uuid, config_loader) if metadata_uuid else ''
        self._update_metadata_worker = _GsUpdateMetadataWorker(
            geoserver_service, workspace, datastore, published_name, title, abstract, keywords, style_task,
            config_loader, metadata_link_url
        )
        self._update_metadata_worker.done.connect(self._on_standard_metadata_updated)
        self._update_metadata_worker.start()

    @pyqtSlot(bool, str)
    def _on_standard_metadata_updated(self, ok, message):
        self.gs_metadata_updated.emit(ok, message)

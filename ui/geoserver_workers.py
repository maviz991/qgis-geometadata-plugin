# -*- coding: utf-8 -*-
"""
geoserver_workers.py - GeoMetadata Plugin
=====================================
Workers (QThread) usados pelo GeoServerBridge - chamadas REST que não podem
bloquear a UI do QGIS (RNF02 de requisitos_v2.md).
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def _gs_augment_404(exc):
    """Acrescenta uma dica acionável quando o erro de uma ação de "Atualizar" (Camada ou
    Estilo - as duas só fazem sentido numa camada JÁ publicada, via PUT) vem de um 404
    ([GS-404], ver GeoServerService.translate_gs_error): nesse contexto específico, "não
    encontrado" quase sempre significa que a camada não existe de fato nesse Workspace/
    Datastore no GeoServer (nunca foi publicada, ou foi removida/renomeada desde a última
    vez) - não um erro genérico de configuração. Não mexe no texto de outros erros."""
    message = str(exc)
    if '[GS-404]' in message:
        message += (
            '<br><br>Isso costuma significar que essa camada não existe de fato nesse '
            'Workspace/Datastore no GeoServer agora (nunca foi publicada, ou foi removida/'
            'renomeada desde a última vez). Confira a aba Destino e use "Serviços > '
            'Publicar Camada" se for o caso.'
        )
    return message


class _GsWorkspacesWorker(QThread):
    """Lista os workspaces do GeoServer em background (RF01)."""
    done = pyqtSignal(list, str)  # workspaces, error

    def __init__(self, geoserver_service, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._config = config_loader_instance

    def run(self):
        try:
            workspaces = self._service.list_workspaces(self._config)
            self.done.emit(workspaces, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsDatastoresWorker(QThread):
    """Lista os datastores de um workspace do GeoServer em background (RF01)."""
    done = pyqtSignal(list, str)  # datastores, error

    def __init__(self, geoserver_service, workspace, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._config = config_loader_instance

    def run(self):
        try:
            datastores = self._service.list_datastores(self._workspace, self._config)
            self.done.emit(datastores, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsFeatureTypesWorker(QThread):
    """Lista as tabelas visíveis (list=all) de um datastore em background - usado pra
    validar, antes de publicar, se a tabela da camada ativa existe ali (ver
    GeoServerService.list_featuretypes)."""
    done = pyqtSignal(list, str)  # nomes, error

    def __init__(self, geoserver_service, workspace, datastore, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._config = config_loader_instance

    def run(self):
        try:
            names = self._service.list_featuretypes(self._workspace, self._datastore, self._config)
            self.done.emit(names, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsFindDatastoreWorker(QThread):
    """Varre todos os workspaces/datastores procurando onde a tabela da camada ativa
    está visível (botão "Detectar automaticamente" - ver GeoServerService.
    find_datastore_for_table). Pode demorar bem mais que os outros workers (1 chamada por
    workspace + 1 por datastore), por isso emite progress() a cada workspace verificado."""
    progress = pyqtSignal(str)  # mensagem de status
    done = pyqtSignal(list, str)  # [{'workspace':..., 'datastore':...}, ...], error

    def __init__(self, geoserver_service, table_name, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._table_name = table_name
        self._config = config_loader_instance

    def run(self):
        try:
            matches = self._service.find_datastore_for_table(
                self._table_name, self._config, progress_callback=self.progress.emit
            )
            self.done.emit(matches, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsPublishWorker(QThread):
    """Registra uma tabela PostGIS já existente como FeatureType no GeoServer (RF02) e,
    quando há uma tarefa de estilo (style_task, ver GeoServerBridge._prepare_style_task),
    sobe/associa o SLD como estilo padrão logo em seguida - tudo fora da UI thread (RNF02).
    Falha no ESTILO não derruba a publicação (que já deu certo): emite sucesso=True com a
    mensagem de aviso preenchida - o JS mostra o aviso e o bridge NÃO grava os campos de
    estilo no banco (pro badge continuar acusando a pendência)."""
    done = pyqtSignal(bool, str, str)  # sucesso, mensagem (erro OU aviso de estilo), nome_publicado

    def __init__(self, geoserver_service, workspace, datastore, native_table_name, published_name,
                 title, abstract, keywords, config_loader_instance, style_task=None, srs=None,
                 metadata_link_url=None):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._native_table_name = native_table_name
        self._published_name = published_name
        self._title = title
        self._abstract = abstract
        self._keywords = keywords
        self._config = config_loader_instance
        self._style_task = style_task
        self._srs = srs
        self._metadata_link_url = metadata_link_url

    def run(self):
        try:
            self._service.register_postgis_featuretype(
                self._workspace, self._datastore, self._native_table_name,
                self._published_name, self._config, self._title, self._abstract, self._keywords,
                srs=self._srs, metadata_link_url=self._metadata_link_url
            )
        except Exception as exc:
            self.done.emit(False, str(exc), self._published_name)
            return
        style_warning = ''
        if self._style_task:
            try:
                self._service.apply_style(self._workspace, self._published_name, self._style_task, self._config)
            except Exception as exc:
                style_warning = (
                    'A camada foi publicada, mas o estilo não pôde ser aplicado: ' + str(exc) +
                    '<br><br>Ajuste a aba Estilos e use "Serviços > Atualizar Estilo" pra tentar de novo.'
                )
        self.done.emit(True, style_warning, self._published_name)


class _GsPullLayerWorker(QThread):
    """"Serviços > Baixar Camada" (banner "Atualização disponível", como o GN) - PULL,
    não push: busca o que está DE FATO publicado no GeoServer agora (título/resumo/
    palavras-chave via fetch_published_featuretype, estilo padrão/adicionais via
    fetch_layer_styles - as duas só leitura, já usadas pelo badge) e devolve pro bridge
    aplicar no formulário local. Existe porque, num fluxo com mais de um técnico na mesma
    camada, "diferente do servidor" pode significar que ALGUÉM MAIS publicou depois de
    você - nesse caso empurrar o formulário local (desatualizado) sobrescreveria o
    trabalho de quem publicou por último. Ver GeoServerService.fetch_published_featuretype/
    fetch_layer_styles."""
    done = pyqtSignal(bool, 'QVariant', str)  # sucesso, dados (title/abstract/keywords/default_style/...), erro

    def __init__(self, geoserver_service, workspace, datastore, published_name, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._published_name = published_name
        self._config = config_loader_instance

    def run(self):
        try:
            remote = self._service.fetch_published_featuretype(
                self._workspace, self._datastore, self._published_name, self._config
            )
            if remote is None:
                self.done.emit(False, {}, (
                    '[GS-404] Essa camada não foi encontrada nesse Workspace/Datastore no '
                    'GeoServer agora - pode nunca ter sido publicada, ou ter sido removida/'
                    'renomeada. Confira a aba Destino e use "Serviços > Publicar Camada" se for o caso.'
                ))
                return
            # Estilo isolado em try/except próprio - mesmo raciocínio de _GsSyncCheckWorker:
            # uma falha aqui não pode jogar fora o título/resumo/palavras-chave já obtidos.
            styles = None
            try:
                styles = self._service.fetch_layer_styles(self._workspace, self._published_name, self._config)
            except Exception as style_exc:
                print(f"GeoMetadata [_GsPullLayerWorker] fetch_layer_styles: {style_exc}")
            remote['default_style'] = (styles or {}).get('default_style') or ''
            remote['default_style_workspace'] = (styles or {}).get('default_style_workspace') or ''
            remote['additional_styles'] = (styles or {}).get('additional') or []
            self.done.emit(True, remote, '')
        except Exception as exc:
            self.done.emit(False, {}, str(exc))


class _GsStylesWorker(QThread):
    """Lista os estilos disponíveis (globais + do workspace) em background - popula o
    select "Usar estilo existente" da aba Estilos (ver GeoServerService.list_styles)."""
    done = pyqtSignal(list, str)  # [{'name':..., 'workspace': ''|ws}], error

    def __init__(self, geoserver_service, workspace, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._config = config_loader_instance

    def run(self):
        try:
            styles = self._service.list_styles(self._workspace, self._config)
            self.done.emit(styles, '')
        except Exception as exc:
            self.done.emit([], str(exc))


class _GsApplyStyleWorker(QThread):
    """Aplica um estilo a uma camada JÁ publicada ("Serviços > Atualizar Estilo") sem
    republicar o FeatureType - upload do SLD (quando há corpo) + defaultStyle, fora da UI
    thread (RNF02). Ver GeoServerService.apply_style."""
    done = pyqtSignal(bool, str)  # sucesso, mensagem de erro

    def __init__(self, geoserver_service, layer_workspace, published_name, style_task, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._layer_workspace = layer_workspace
        self._published_name = published_name
        self._style_task = style_task
        self._config = config_loader_instance

    def run(self):
        try:
            self._service.apply_style(self._layer_workspace, self._published_name, self._style_task, self._config)
            self.done.emit(True, '')
        except Exception as exc:
            self.done.emit(False, _gs_augment_404(exc))


class _GsSyncCheckWorker(QThread):
    """Confere ao vivo (REST, GeoServerService.fetch_published_featuretype) se o
    formulário bate com o que está DE FATO publicado no GeoServer agora - nível 'sistema'
    do badge (ver GeoServerBridge.check_gs_sync). Chamada de rede isolada da UI thread
    (RNF02) - antes rodava direto no slot pyqtSlot, travando o painel GS inteiro enquanto
    esperava a resposta."""
    done = pyqtSignal('QVariant')  # {'state': 'sys_synced'|'sys_modified'|'sys_not_found'|'error', 'workspace':, 'datastore':, 'published_name':, [+ 'title'/'abstract'/'keywords' ao vivo quando encontrado]}

    def __init__(self, geoserver_service, workspace, datastore, published_name, title, abstract, keywords, config_loader_instance, style_cfg=None):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._published_name = published_name
        self._title = title
        self._abstract = abstract
        self._keywords = keywords
        self._config = config_loader_instance
        self._style_cfg = style_cfg

    def run(self):
        # workspace/datastore/published_name sempre presentes no resultado - o JS usa isso
        # pra confirmar que a resposta ainda corresponde à checagem que ele espera (camada/
        # destino pode ter trocado enquanto essa chamada estava em voo).
        base = {'workspace': self._workspace, 'datastore': self._datastore, 'published_name': self._published_name}
        try:
            remote = self._service.fetch_published_featuretype(
                self._workspace, self._datastore, self._published_name, self._config
            )
            if remote is None:
                base['state'] = 'sys_not_found'
                self.done.emit(base)
                return
            remote_kw = sorted((k or '').strip() for k in (remote.get('keywords') or []))
            local_kw = sorted((k or '').strip() for k in (self._keywords or []))
            title_match = (remote.get('title') or '').strip() == (self._title or '').strip()
            abstract_match = (remote.get('abstract') or '').strip() == (self._abstract or '').strip()
            kw_match = remote_kw == local_kw
            matches = title_match and abstract_match and kw_match
            # Log de diagnóstico temporário (não é logging permanente do projeto) - "matches"
            # antes era um booleano só, sem dizer QUAL campo diverge; imprime os dois lados
            # só quando dá falso, pra não gerar ruído numa checagem que bateu certinho.
            if not matches:
                print(
                    f"GeoMetadata [_GsSyncCheckWorker] DIVERGÊNCIA título/resumo/keywords - "
                    f"title: match={title_match} remoto={remote.get('title')!r} local={self._title!r} | "
                    f"abstract: match={abstract_match} remoto={remote.get('abstract')!r} local={self._abstract!r} | "
                    f"keywords: match={kw_match} remoto={remote_kw!r} local={local_kw!r}"
                )
            base.update(remote)

            # Checagem de estilos ao vivo - isolada em try/except próprio: uma falha aqui
            # (timeout, layer ainda não exposta como resource /rest/layers logo após
            # publicar, etc.) não pode derrubar a checagem inteira pra 'error' e descartar
            # o resultado (já calculado acima) do match de título/resumo/palavras-chave.
            remote_styles = None
            try:
                remote_styles = self._service.fetch_layer_styles(
                    self._workspace, self._published_name, self._config
                )
            except Exception as style_exc:
                print(f"GeoMetadata [_GsSyncCheckWorker] fetch_layer_styles: {style_exc}")

            styles_match = True
            if remote_styles is not None:
                base['remote_default_style'] = remote_styles.get('default_style')
                base['remote_default_style_workspace'] = remote_styles.get('default_style_workspace')
                base['remote_additional_styles'] = remote_styles.get('additional') or []

                # Só compara quando conseguimos buscar o estado remoto de verdade - sem
                # isso (fetch falhou ou a camada não existe como 'layer' resource),
                # styles_match fica True (mesmo comportamento de antes dessa feature
                # existir) em vez de acusar divergência por uma checagem que não rodou.
                if self._style_cfg:
                    from .geoserver_bridge import GeoServerBridge
                    d_src, d_nm, d_ws, adds_json = GeoServerBridge.derive_style_fields(self._style_cfg, self._workspace)
                    if d_src:
                        r_def = remote_styles.get('default_style') or ''
                        if r_def != d_nm:
                            styles_match = False
                            print(f"GeoMetadata [_GsSyncCheckWorker] DIVERGÊNCIA estilo padrão - remoto={r_def!r} local(d_nm)={d_nm!r} style_cfg={self._style_cfg!r}")

                        if styles_match:
                            import json
                            adds = json.loads(adds_json) if adds_json else []
                            r_adds = remote_styles.get('additional') or []
                            r_adds_list = [(a.get('name') or '', a.get('style_workspace') or '') for a in r_adds]
                            # workspace vazio só cai pro workspace de publicação quando o
                            # estilo foi CRIADO nessa publicação ('file'/'qgis' - aí sim
                            # sempre nasce no workspace de destino, mesma regra de
                            # derive_style_fields/_extract). Pra um estilo 'existing'
                            # (já existente, escolhido da lista), workspace vazio é um
                            # ESTILO GLOBAL de verdade - forçar o workspace de publicação
                            # aqui inventava uma divergência contra o lado remoto (que
                            # corretamente reporta '' pra estilo global).
                            local_adds_list = [
                                (
                                    a.get('existing_name') or a.get('name') or '',
                                    (a.get('existing_workspace') or '') if a.get('source') == 'existing' else self._workspace
                                )
                                for a in adds
                            ]

                            if len(r_adds_list) != len(local_adds_list):
                                styles_match = False
                                print(f"GeoMetadata [_GsSyncCheckWorker] DIVERGÊNCIA estilos adicionais (quantidade) - remoto={r_adds_list!r} local={local_adds_list!r}")
                            else:
                                for la in local_adds_list:
                                    if la not in r_adds_list:
                                        styles_match = False
                                        print(f"GeoMetadata [_GsSyncCheckWorker] DIVERGÊNCIA estilos adicionais (item) - remoto={r_adds_list!r} local={local_adds_list!r}")
                                        break

            base['state'] = 'sys_synced' if (matches and styles_match) else 'sys_modified'
            self.done.emit(base)
        except Exception as exc:
            print(f"GeoMetadata [_GsSyncCheckWorker]: {exc}")
            # base (workspace/datastore/published_name) preservado mesmo no erro - ver
            # comentário equivalente em GeoServerBridge.check_gs_sync sobre a resposta
            # precisar bater a key esperada em _onGsSyncChecked (geoserver.js).
            base['state'] = 'error'
            self.done.emit(base)


class _GsActiveLayerInfoWorker(QThread):
    """Busca em background o que está salvo no banco pra camada ativa (metadado MGB +
    destino de publicação GS, GeoServerService.fetch_saved_records) e, se achar um uuid,
    o metadado AO VIVO no GeoNetwork - usado por GeoServerBridge.get_active_layer_publish_info.
    Antes essa busca rodava toda inteira, síncrona, dentro do próprio pyqtSlot (duas
    conexões psycopg2 + potencialmente uma chamada REST ao GeoNetwork, todas bloqueantes) -
    travava a UI inteira (Qt event loop, inclusive o compositor da QWebEngineView) toda vez
    que o painel GS abria ou a camada ativa mudava, sem exceção (RNF02 - mesmo motivo de
    _GsSyncCheckWorker). Só recebe dados já resolvidos na main thread (conn_params via
    resolve_layer_db_params, uuid_hint já combinando draft+hint) - nada aqui toca a API do
    QGIS (QgsVectorLayer etc.), que não é thread-safe."""
    done = pyqtSignal('QVariant')  # {'local_metadata': dict|None, 'saved_destination': dict|None, 'gn_remote': dict|None, 'db_error': bool}

    def __init__(self, conn_params, f_table_catalog, f_table_schema, f_table_name,
                 uuid_hint, geonetwork_service, config_loader_instance):
        super().__init__()
        self._conn_params = conn_params
        self._f_table_catalog = f_table_catalog
        self._f_table_schema = f_table_schema
        self._f_table_name = f_table_name
        self._uuid_hint = uuid_hint
        self._geonetwork_service = geonetwork_service
        self._config = config_loader_instance

    def run(self):
        from ..core.geoserver_service import GeoServerService
        local_metadata, saved_destination = None, None
        db_error = False
        try:
            local_metadata, saved_destination = GeoServerService.fetch_saved_records(
                self._conn_params, self._f_table_catalog, self._f_table_schema, self._f_table_name
            )
        except Exception as exc:
            if psycopg2 and isinstance(exc, psycopg2.OperationalError):
                # Banco inacessível agora (ver fetch_saved_records) - diferente de "nada
                # salvo" - GeoServerBridge._on_layer_info_ready repassa esse flag pro JS
                # avisar o usuário em vez de mostrar "Não Encontrado" silenciosamente.
                db_error = True
            else:
                print(f"GeoMetadata [_GsActiveLayerInfoWorker] banco: {exc}")

        # Mesma prioridade de uuid de antes (_load_layer_metadata): metadata_uuid do banco
        # primeiro, senão o hint (que já embute o do rascunho local, resolvido na main
        # thread antes de disparar esse worker - ver get_active_layer_publish_info).
        gn_remote = None
        uuid = (local_metadata or {}).get('metadata_uuid') or self._uuid_hint or None
        if uuid and self._geonetwork_service:
            try:
                gn_remote = self._geonetwork_service.fetch_from_geonetwork(uuid, self._config)
            except Exception as exc:
                print(f"GeoMetadata [_GsActiveLayerInfoWorker] GeoNetwork: {exc}")

        self.done.emit({
            'local_metadata': local_metadata,
            'saved_destination': saved_destination,
            'gn_remote': gn_remote,
            'db_error': db_error,
        })

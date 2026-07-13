# -*- coding: utf-8 -*-
"""
geoserver_workers.py - GeoMetadata Plugin
=====================================
Workers (QThread) usados pelo GeoServerBridge - chamadas REST que não podem
bloquear a UI do QGIS (RNF02 de requisitos_v2.md).
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal


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
    """Registra uma tabela PostGIS já existente como FeatureType no GeoServer (RF02) —
    única chamada de rede desse fluxo, isolada da UI thread (RNF02)."""
    done = pyqtSignal(bool, str, str)  # sucesso, mensagem, nome_publicado

    def __init__(self, geoserver_service, workspace, datastore, native_table_name, published_name,
                 title, abstract, keywords, config_loader_instance):
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

    def run(self):
        try:
            self._service.register_postgis_featuretype(
                self._workspace, self._datastore, self._native_table_name,
                self._published_name, self._config, self._title, self._abstract, self._keywords
            )
            self.done.emit(True, '', self._published_name)
        except Exception as exc:
            self.done.emit(False, str(exc), self._published_name)

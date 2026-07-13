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

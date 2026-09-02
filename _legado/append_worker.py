with open("ui/geoserver_workers.py", "a", encoding="utf-8") as f:
    f.write("""

class _GsUpdateMetadataWorker(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, geoserver_service, workspace, datastore, published_name, title, abstract, keywords, style_json, config_loader_instance):
        super().__init__()
        self._service = geoserver_service
        self._workspace = workspace
        self._datastore = datastore
        self._published_name = published_name
        self._title = title
        self._abstract = abstract
        self._keywords = keywords
        self._style_json = style_json
        self._config = config_loader_instance

    def run(self):
        try:
            self._service.update_published_featuretype(
                self._workspace, self._datastore, self._published_name, self._config,
                title=self._title, abstract=self._abstract, keywords=self._keywords
            )
            import json
            style_cfg = None
            if self._style_json:
                try:
                    style_cfg = json.loads(self._style_json)
                except Exception:
                    pass
            if style_cfg and style_cfg.get('type') != 'sys_keep':
                try:
                    self._service.apply_style(self._workspace, self._published_name, style_cfg, self._config)
                except Exception as exc:
                    self.done.emit(False, f'Metadados atualizados, mas falha ao aplicar estilo: {str(exc)}')
                    return

            self.done.emit(True, 'Metadados atualizados com sucesso.')
        except Exception as exc:
            self.done.emit(False, str(exc))
""")

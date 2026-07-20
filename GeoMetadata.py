# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GeoMetadata
                                 A QGIS plugin
                              -------------------
        copyright            : (C) 2025 by Matheus Aviz
        email                : mdaviz@apoiocdhu.sp.gov.br
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .GeoMetadata_dialog import GeoMetadataDialog
import os.path


class GeoMetadata:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'GeoMetadata_{}.qm'.format(locale))

        self.api_session = None
        self.auth_username = None   # Armazena o username independente do método de auth
        # Sessão separada EXCLUSIVAMENTE para a API REST do GeoServer - necessária quando
        # o usuário está logado via EntraID (SSO), mas o Security Proxy do GeoOrchestra
        # não aceita o Bearer token do Azure AD nas chamadas REST (aud incorreto). Nesses
        # casos, o usuário pode configurar credenciais admin separadas para o GeoServer
        # (armazenadas no QGIS Auth Manager) - o SSO continua válido para o GeoNetwork.
        # Se None, as chamadas REST usam api_session como fallback (admin local funciona).
        self.gs_rest_session = None
        self.gs_rest_username = None  # username das credenciais admin do GeoServer REST

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&GeoMetadata')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'GeoMetadata')
        self.toolbar.setObjectName(u'GeoMetadata')

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('GeoMetadata', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            # Customize the iface method if you want to add to a specific
            # menu (for example iface.addToVectorMenu):
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        self.dlg = None  # referência à instância atual do diálogo - ver run()

        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.add_action(
            icon_path,
            text=self.tr(u'GeoMetadata'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # Verifica e instala msal em background após QGIS carregar completamente
        QTimer.singleShot(3000, self._check_and_install_dependencies)

    def _check_and_install_dependencies(self):
        from .core.env_checker import check_and_run_setup
        check_and_run_setup(parent=self.iface.mainWindow())


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        # Diálogo agora é não-modal (ver run()) - pode continuar aberto na tela quando o
        # plugin é recarregado/desabilitado (Plugin Reloader etc.), o que não acontecia
        # antes (exec_() bloqueava até o diálogo fechar). Fecha explicitamente pra não
        # deixar uma janela órfã, sem bridge/ação nenhuma funcionando por trás.
        if getattr(self, 'dlg', None) is not None:
            try:
                self.dlg.close()
            except RuntimeError:
                pass
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&GeoMetadata'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar


    def run(self):
        """Run method that performs all the real work"""
        # Guarda contra dialog duplicado (reentrância em run() já causou crash nativo -
        # access violation - com dois QDialog abertos/QDialog.exec_() aninhados, stack
        # trace com QToolButton::mouseReleaseEvent duplicado). A guarda ANTES usava
        # QDialog.exec_() (bloqueante) + uma flag zerada só quando o diálogo fechava - só
        # que exec_() torna o diálogo modal (WindowModal) em relação à janela principal do
        # QGIS, bloqueando interação com o QGIS (trocar camada ativa, mexer no mapa)
        # enquanto o painel está aberto - o oposto do que o plugin precisa, já que ele
        # depende de bridge.layer_changed/iface.activeLayer() pra reagir à camada ativa
        # trocando DURANTE a sessão. Não-modal (show()) resolve isso; a guarda agora checa
        # se já existe uma instância visível em vez de "ainda dentro do exec_() bloqueante".
        if getattr(self, 'dlg', None) is not None:
            try:
                if self.dlg.isVisible():
                    self.dlg.raise_()
                    self.dlg.activateWindow()
                    return
            except RuntimeError:
                pass  # wrapped C++ object já foi deletado - segue e cria uma instância nova
        self.dlg = GeoMetadataDialog(iface=self.iface,
                                     plugin_instance=self,
                                     parent=self.iface.mainWindow())
        self.dlg.show()

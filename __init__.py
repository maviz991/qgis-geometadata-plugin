# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GeoMetadata
                                 A QGIS plugin
 Description
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
 This script initializes the plugin, making it known to QGIS.
"""

# Força o compartilhamento de contexto OpenGL necessário pelo PyQtWebEngine
# Deve ser definido o mais cedo possível no carregamento do plugin
from qgis.PyQt.QtCore import Qt, QCoreApplication
try:
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
except:
    pass

# Tenta pré-importar o WebEngine para evitar erros de inicialização posterior
try:
    from qgis.PyQt import QtWebEngineWidgets
except:
    pass


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load GeoMetadata class from file GeoMetadata.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .GeoMetadata import GeoMetadata
    return GeoMetadata(iface)

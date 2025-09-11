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


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load GeoMetadata class from file GeoMetadata.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .GeoMetadata import GeoMetadata
    return GeoMetadata(iface)

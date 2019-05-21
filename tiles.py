import datetime
import requests
import webbrowser

from . import auth
from . import resources
from .utils import log, tr

from qgis.PyQt.QtCore import QSettings
from qgis.core import QgsRasterLayer, QgsProject


class TilesManager:

    tiles = {
        "dark-matter": {
            "label": tr("Dark Matter"),
            "resource": resources.tiles_preview_darkmatter,
        },
        "positron": {
            "label": tr("Positron"),
            "resource": resources.tiles_preview_positron,
        },
        "klokantech-basic": {
            "label": tr("Klokantech-Basic"),
            "resource": resources.tiles_preview_klokantech,
        },
        "osm-bright": {
            "label": tr("OSM Bright"),
            "resource": resources.tiles_preview_osm,
        },
    }

    def __init__(self):
        self.has_tiles = self._check_has_tiles()

    def _get_url(self, identifier):
        app_id, _ = auth.get_app_id_and_api_key()
        disable_https = QSettings().value(
            "travel_time_platform/disable_https", False, type=bool
        )
        return "https://tiles.traveltimeplatform.com/styles/{identifier}/{{z}}/{{x}}/{{y}}.png?key={app_id}".format(
            app_id=app_id, identifier=identifier, verify=not disable_https
        )

    def _check_has_tiles(self):
        test_url = self._get_url(list(self.tiles.keys())[0])
        response = requests.get(test_url.format(z=12, x=2048, y=1361))
        return response.ok

    def add_layer(self, identifier):
        layer = QgsRasterLayer(
            "type=xyz&url=" + self._get_url(identifier),
            self.tiles[identifier]["label"],
            "wms",
        )
        QgsProject.instance().addMapLayer(layer)

    def request_access(self):
        webbrowser.open("https://docs.traveltimeplatform.com/tiles/getting-started/")


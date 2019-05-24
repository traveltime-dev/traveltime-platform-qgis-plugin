import datetime
import requests
import webbrowser

from . import auth
from . import resources
from .utils import log, tr

from qgis.PyQt.QtCore import QSettings
from qgis.core import QgsRasterLayer, QgsProject, Qgis


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

    def __init__(self, main):
        self.main = main

    def _get_url(self, identifier):
        app_id, _ = auth.get_app_id_and_api_key()
        disable_https = QSettings().value(
            "traveltime_platform/disable_https", False, type=bool
        )
        return "https://tiles.traveltimeplatform.com/styles/{identifier}/{{z}}/{{x}}/{{y}}.png?key={app_id}".format(
            app_id=app_id, identifier=identifier, verify=not disable_https
        )

    def add_tiles_to_browser(self):
        # We test access to tiles with API
        test_url = self._get_url(list(self.tiles.keys())[0])
        response = requests.get(test_url.format(z=12, x=2048, y=1361))
        has_tiles = response.ok

        if not has_tiles:
            self.main.iface.messageBar().pushMessage(
                "Info",
                tr(
                    "TravelTime also offers some background maps for their users. <a href='https://docs.traveltimeplatform.com/tiles/getting-started/'>Click here to request access !</a>"
                ),
                level=Qgis.Info,
            )
        else:

            for identifier, tile in self.tiles.items():
                url = self._get_url(identifier)
                label = "TravelTime - " + tile["label"]

                settings_base = "qgis/connections-xyz/" + label

                QSettings().setValue(settings_base + "/url", url)
                QSettings().setValue(settings_base + "/zmax", 20)
                QSettings().setValue(settings_base + "/zmin", 0)

                # Update GUI
                self.main.iface.reloadConnections()

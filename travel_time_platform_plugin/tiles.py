import requests
from qgis.core import Qgis
from qgis.PyQt.QtCore import QSettings

from . import auth
from .utils import tr


class TilesManager:

    tiles = {
        "lux": tr("Lux"),
    }

    def __init__(self, main):
        self.main = main

    def _get_url(self, identifier):
        app_id, _ = auth.get_app_id_and_api_key()
        disable_https = QSettings().value(
            "traveltime_platform/disable_https", False, type=bool
        )
        return "https://tiles.traveltime.com/{identifier}/{{z}}/{{x}}/{{y}}.png?key={app_id}&client=QGIS".format(
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
                    "TravelTime also offers some background maps for their users. <a href='https://docs.traveltime.com/api/tiles/getting-started'>Click here to request access !</a>"
                ),
                level=Qgis.Info,
            )
        else:

            for identifier, label in self.tiles.items():
                url = self._get_url(identifier)
                label = "TravelTime - " + label

                settings_base = "qgis/connections-xyz/" + label

                QSettings().setValue(settings_base + "/url", url)
                QSettings().setValue(settings_base + "/zmax", 20)
                QSettings().setValue(settings_base + "/zmin", 0)
                QSettings().setValue(settings_base + "/tilePixelRatio", 2)

                # Update GUI
                self.main.iface.reloadConnections()

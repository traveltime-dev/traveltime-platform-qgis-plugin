import requests
from qgis.core import Qgis, QgsSettings
from qgis.PyQt.QtCore import QSettings

from . import auth
from .utils import log, tr

LABEL_PREFIX = "TravelTime - "


class TilesManager:
    tiles = {
        "osm-bright": tr("OSM Bright"),
        "positron": tr("Positron"),
    }

    def __init__(self, main):
        self.main = main

    def browser_label(self, identifier):
        return LABEL_PREFIX + self.tiles[identifier]

    def _get_url(self, identifier):
        app_id, _ = auth.get_app_id_and_api_key()
        return "https://tiles.traveltimeapp.com/{identifier}/{{z}}/{{x}}/{{y}}.png?key={app_id}&client=QGIS".format(
            app_id=app_id, identifier=identifier
        )

    def _drop_retired_entries(self):
        """A renamed or retired style would otherwise leave a dead browser entry"""
        current = {self.browser_label(identifier) for identifier in self.tiles}
        s = QgsSettings()
        s.beginGroup("connections/xyz/items")
        for label in s.childGroups():
            if not label.startswith(LABEL_PREFIX) or label in current:
                continue
            # only ours: the user may have kept an entry of their own under the prefix
            if "traveltime" in s.value(f"{label}/url", ""):
                s.remove(label)
        s.endGroup()

    def add_tiles_to_browser(self):
        """Returns False when the layers were not registered, so callers do not
        add a second, contradictory reason for their absence."""
        self._drop_retired_entries()
        self.main.iface.reloadConnections()

        # We test access to tiles with API
        test_url = self._get_url(next(iter(self.tiles)))
        verify = not QSettings().value(
            "traveltime_platform/disable_https", False, type=bool
        )
        try:
            response = requests.get(
                test_url.format(z=12, x=2048, y=1361), timeout=10, verify=verify
            )
        except OSError as e:
            # Not the exception itself: it stringifies the app id in the url
            log("Could not reach the tiles service ({})".format(type(e).__name__))
            self.main.iface.messageBar().pushMessage(
                "Warning",
                tr("Could not reach the TravelTime tiles service."),
                level=Qgis.MessageLevel.Warning,
            )
            return False

        # A proxy block page answers 200, so require an actual image
        has_tiles = response.ok and response.content[:4] == b"\x89PNG"

        if not has_tiles:
            self.main.iface.messageBar().pushMessage(
                "Info",
                tr(
                    "TravelTime also offers some background maps for their users. <a href='https://docs.traveltime.com/api/tiles/getting-started'>Click here to request access !</a>"
                ),
                level=Qgis.MessageLevel.Info,
            )
            return False

        s = QgsSettings()
        for identifier in self.tiles:
            settings_path = f"connections/xyz/items/{self.browser_label(identifier)}"
            s.setValue(f"{settings_path}/url", self._get_url(identifier))
            s.setValue(f"{settings_path}/zmax", 20)
            s.setValue(f"{settings_path}/zmin", 0)
            s.setValue(f"{settings_path}/tilePixelRatio", 2)

        self.main.iface.reloadConnections()
        return True

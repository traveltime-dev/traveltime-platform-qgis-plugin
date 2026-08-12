import os

from qgis.PyQt.QtCore import QSettings, QStandardPaths

from .constants import CREDENTIAL_HEADERS
from .libraries import requests_cache
from .libraries.requests_cache.backends import DbCache
from .utils import log

PURGED_SETTING = "traveltime_platform/cache_credentials_purged"
SIBLINGS_PURGED_SETTING = "traveltime_platform/sibling_caches_purged"


class CredentialFreeCache(DbCache):
    def _picklable_field(self, response, name):
        value = super()._picklable_field(response, name)
        if name == "request":
            # super() only shallow-copies, so these are still the live request's headers
            value.headers = value.headers.copy()
            for header in CREDENTIAL_HEADERS:
                value.headers.pop(header, None)
        return value


class Cache:
    def __init__(self):
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )

        if not os.path.exists(base):
            os.makedirs(base, exist_ok=True)
        self.path = os.path.join(base, "ttp_cache.sqlite")

        self.cached_requests = None

        self.prepare()

    def clear(self):
        self.cached_requests.cache.clear()

    def size(self):
        if os.path.exists(self.path):
            num = os.path.getsize(self.path)
            # https://gist.github.com/cbwar/d2dfbc19b140bd599daccbe0fe925597
            for unit in ["", "k", "M", "G", "T", "P", "E", "Z"]:
                if abs(num) < 1024.0:
                    return "%3.1f %s%s" % (num, unit, "b")
                num /= 1024.0
            return "%.1f%s%s" % (num, "Yi", "b")
        return "0b"

    def prepare(self):
        cache_name = os.path.splitext(self.path)[0]
        self.cached_requests = requests_cache.core.CachedSession(
            cache_name=cache_name,
            backend=CredentialFreeCache(cache_name),
            expire_after=86400,
            allowable_methods=("GET", "POST"),
        )
        self._purge_credentials_once()

    def _purge_credentials_once(self):
        """Entries from earlier versions hold credentials, and nothing else evicts them.

        Tracked per cache file: a sibling another QGIS holds open must be retried
        without re-wiping this generation's healthy cache every start.
        """
        settings = QSettings()
        if not settings.value(PURGED_SETTING, False, type=bool):
            try:
                self.clear()
            except Exception as e:
                # runs during plugin import, and vacuum needs the file to itself
                log(f"Could not purge the response cache, will retry next start: {e}")
            else:
                settings.setValue(PURGED_SETTING, True)

        if settings.value(SIBLINGS_PURGED_SETTING, False, type=bool):
            return
        # Cleared, not unlinked: that QGIS creates its tables only at startup
        cleared = True
        for path in self._sibling_cache_paths():
            try:
                DbCache(os.path.splitext(path)[0]).clear()
            except Exception as e:
                log(f"Could not clear a cache of another QGIS generation: {e}")
                cleared = False
        if cleared:
            settings.setValue(SIBLINGS_PURGED_SETTING, True)

    def _generations_root(self):
        """Splits our cache path into the dir holding one entry per QGIS generation
        and the part below it, which Windows nests under an extra "cache" level."""
        relative = os.path.basename(self.path)
        generation = os.path.dirname(self.path)
        if os.path.basename(generation).lower() == "cache":
            relative = os.path.join(os.path.basename(generation), relative)
            generation = os.path.dirname(generation)
        return os.path.dirname(generation), relative

    def _sibling_cache_paths(self):
        """CacheLocation is per QGIS generation, so the other generation's file is ours"""
        generations, relative = self._generations_root()
        # normalised: Qt reports / separators where os.path.join would write \
        ours = os.path.normcase(os.path.normpath(self.path))
        paths = (
            os.path.join(generations, d, relative) for d in os.listdir(generations)
        )
        return [
            p
            for p in paths
            if os.path.normcase(os.path.normpath(p)) != ours and os.path.isfile(p)
        ]


instance = Cache()

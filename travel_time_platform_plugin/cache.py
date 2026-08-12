import os

from qgis.PyQt.QtCore import QSettings, QStandardPaths

from .constants import CREDENTIAL_HEADERS
from .libraries import requests_cache
from .libraries.requests_cache.backends import DbCache
from .utils import log

PURGED_SETTING = "traveltime_platform/cache_credentials_purged"


class CredentialFreeCache(DbCache):
    """Sqlite cache that keeps API credentials out of the cache file."""

    def _picklable_field(self, response, name):
        value = super()._picklable_field(response, name)
        if name == "request":
            # copy rather than mutate: the copy shares the live request's headers
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
        """Entries written before CredentialFreeCache still hold the credentials.

        Nothing evicts them on its own: expired entries go only when the same key
        is requested again, so a one-off search would keep them indefinitely.
        """
        settings = QSettings()
        if settings.value(PURGED_SETTING, False, type=bool):
            return
        try:
            self.clear()
        except Exception as e:
            # runs during plugin import, and vacuum needs the file to itself
            log(f"Could not purge the response cache, will retry next start: {e}")
            return
        settings.setValue(PURGED_SETTING, True)


instance = Cache()

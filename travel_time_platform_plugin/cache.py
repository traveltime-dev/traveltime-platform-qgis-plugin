from datetime import timedelta, datetime
import os

from qgis.PyQt.QtCore import QCoreApplication, QStandardPaths, QSettings

from .libraries import requests_cache

from .utils import log


class Cache:
    def __init__(self):

        base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)

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
        self.cached_requests = requests_cache.core.CachedSession(
            cache_name=os.path.splitext(self.path)[0],
            backend="sqlite",
            expire_after=86400,
            allowable_methods=("GET", "POST"),
        )

    def throttling_info(self):
        """
        Returns how long we must wait in seconds before next request according to throttling settings
        """
        throttle = QSettings().value("traveltime_platform/throttle_calls_enabled", False, type=bool)
        throttle_value = QSettings().value("traveltime_platform/throttle_calls_value", 300, type=int)

        if not throttle:
            return False

        date = datetime.utcnow() - timedelta(seconds=60)
        oldest = datetime.utcnow()
        count = 0
        for key in self.cached_requests.cache.responses:
            try:
                response, created_at = self.cached_requests.cache.responses[key]
            except KeyError:
                continue
            if created_at >= date:
                oldest = min(oldest, created_at)
                count += 1

        if count < throttle_value:
            return False

        return (datetime.utcnow() - oldest).seconds




instance = Cache()

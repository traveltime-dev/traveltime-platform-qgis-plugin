import os

from qgis.PyQt.QtCore import QStandardPaths

from .libraries import requests_cache


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


instance = Cache()

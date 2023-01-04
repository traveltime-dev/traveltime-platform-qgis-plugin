import time
from datetime import datetime, timedelta, timezone

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsMessageLog,
)
from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTimeZone

EPSG4326 = QgsCoordinateReferenceSystem("EPSG:4326")

timezones = list([t.data().decode("utf-8") for t in QTimeZone.availableTimeZoneIds()])
default_timezone = QTimeZone.systemTimeZoneId().data().decode("utf-8")
# For some reason, the system timezone is not in the available list in Docker. In this case, fall back to UTC.
if default_timezone not in timezones:
    default_timezone = QTimeZone.utc().id().data().decode("utf-8")


def now_iso():
    """Calculate the offset taking into account daylight saving time

    thanks https://stackoverflow.com/a/28147286"""

    utc_offset_sec = time.altzone if time.localtime().tm_isdst else time.timezone
    utc_offset = timedelta(seconds=-utc_offset_sec)
    now = datetime.now()
    return (
        datetime(year=now.year, month=now.month, day=now.day, hour=now.hour)
        .replace(tzinfo=timezone(offset=utc_offset))
        .isoformat()
    )


def clone_feature(request, source_layer, output_fields=None):
    """Returns a feature cloned from the source layer

    request : QgsFeatureRequest of the source feature
    source_layer : the layer to clone from
    output_fields : QgsFields to initialize the clone (if none, source_layers.fields() will be used)
    """
    if output_fields is None:
        output_fields = source_layer.fields()
    new_feature = QgsFeature(output_fields)
    for old_feature in source_layer.getFeatures(request):
        # Return the first one
        break
    new_feature.setGeometry(QgsGeometry(old_feature.geometry()))
    # Clone all attributes
    for i in range(len(source_layer.fields())):
        new_feature.setAttribute(i, old_feature.attribute(i))
    return new_feature


def log(msg, tag="TimeTravelPlatform", level=Qgis.Info):
    QgsMessageLog.logMessage(str(msg), tag, level=level)


def tr(string):
    return QCoreApplication.translate("@default", string)


class Throttler:

    DURATION = 60

    def __init__(self):
        self.queries = []

    def throttle_query(self, new_search_count):
        """
        Returns 2-uple (throttle_time_in_seconds, recent_seaches_count) required for making new requests according to settings.
        """

        throttle = QSettings().value(
            "traveltime_platform/throttling_enabled", False, type=bool
        )
        if not throttle:
            return 0, -1

        max_searches_count = QSettings().value(
            "traveltime_platform/throttling_max_searches_count", 300, type=int
        )

        threshold = datetime.now() - timedelta(seconds=Throttler.DURATION)

        # Prune old entries
        self.queries = sorted([t for t in self.queries if t[0] >= threshold])

        # Add the searches
        self.queries.append((datetime.now(), new_search_count))

        # See if we must throttle
        recent_searches_count = sum(v[1] for v in self.queries)
        if recent_searches_count > max_searches_count:

            # See how long we must throttle
            tot = 0
            for q in self.queries:
                tot += q[1]
                if tot >= new_search_count:
                    throttle = (
                        Throttler.DURATION - (datetime.now() - q[0]).total_seconds()
                    )
                    break
            else:
                throttle = Throttler.DURATION

            return throttle, recent_searches_count

        return 0, recent_searches_count


throttler = Throttler()

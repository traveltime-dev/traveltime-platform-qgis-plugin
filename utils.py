import datetime
import time

from qgis.PyQt.QtCore import QCoreApplication

from qgis.core import QgsFeature, QgsGeometry, QgsMessageLog


def now_iso():
    """Calculate the offset taking into account daylight saving time

    thanks https://stackoverflow.com/a/28147286"""

    utc_offset_sec = time.altzone if time.localtime().tm_isdst else time.timezone
    utc_offset = datetime.timedelta(seconds=-utc_offset_sec)
    now = datetime.datetime.now()
    return (
        datetime.datetime(year=now.year, month=now.month, day=now.day, hour=now.hour)
        .replace(tzinfo=datetime.timezone(offset=utc_offset))
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


def log(msg):
    QgsMessageLog.logMessage(str(msg), "TimeTravelPlatform")


def tr(string):
    return QCoreApplication.translate("@default", string)

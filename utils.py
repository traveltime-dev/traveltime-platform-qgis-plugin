import datetime
import time

from qgis.PyQt.QtCore import QCoreApplication

def now_iso():
    """Calculate the offset taking into account daylight saving time

    thanks https://stackoverflow.com/a/28147286"""

    utc_offset_sec = time.altzone if time.localtime().tm_isdst else time.timezone
    utc_offset = datetime.timedelta(seconds=-utc_offset_sec)
    now = datetime.datetime.now()
    return datetime.datetime(year=now.year, month=now.month, day=now.day, hour=now.hour).replace(tzinfo=datetime.timezone(offset=utc_offset)).isoformat()

def tr(string):
    return QCoreApplication.translate('@default', string)

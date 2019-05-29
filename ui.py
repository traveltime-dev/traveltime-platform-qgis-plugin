import os
import webbrowser
from qgis.PyQt.QtCore import Qt, QSettings, QDateTime, QDate, QTime, QUrl
from qgis.PyQt.QtWidgets import QDialog, QDateTimeEdit, QWidget
from qgis.PyQt.QtWebKitWidgets import QWebView
from qgis.PyQt import uic

from processing.gui.AlgorithmDialog import AlgorithmDialog
from processing.gui.wrappers import WidgetWrapper

from . import algorithms
from . import auth
from . import cache
from .utils import tr, log


HELP_DIR = os.path.join(os.path.dirname(__file__), "docs")


class ConfigDialog(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui", "ConfigDialog.ui"), self
        )

        self.getKeyButton.pressed.connect(self.get_key)
        self.countResetButton.pressed.connect(self.reset_count)
        self.buttonBox.accepted.connect(self.accept)
        self.clearCacheButton.pressed.connect(self.clear_cache)

    def showEvent(self, *args, **kwargs):
        super().showEvent(*args, **kwargs)

        # Get the current keys
        app_id, api_key = auth.get_app_id_and_api_key()

        self.appIDLineEdit.setText(app_id)
        self.apiKeyLineEdit.setText(api_key)

        # Get the settings
        s = QSettings()
        # warning enabled
        self.warningGroupBox.setChecked(
            s.value("traveltime_platform/warning_enabled", True, type=bool)
        )
        # warning limit
        self.warningSpinBox.setValue(
            s.value("traveltime_platform/warning_limit", 10, type=int)
        )
        # current count
        self.refresh_count_display()
        # logs calls
        self.logCallsCheckBox.setChecked(
            s.value("traveltime_platform/log_calls", False, type=bool)
        )
        # disable https
        self.disableHttpsCheckBox.setChecked(
            s.value("traveltime_platform/disable_https", False, type=bool)
        )
        # refresh current cache
        self.refresh_cache_label()

    def get_key(self):
        webbrowser.open("http://docs.traveltimeplatform.com/overview/getting-keys/")

    def reset_count(self):
        QSettings().setValue("traveltime_platform/current_count", 0)
        self.refresh_count_display()

    def refresh_count_display(self):
        c = QSettings().value("traveltime_platform/current_count", 0, type=int)
        self.countSpinBox.setValue(c)

    def clear_cache(self):
        cache.instance.clear()
        self.refresh_cache_label()

    def refresh_cache_label(self):
        self.cacheLabel.setText(
            tr("Current cache size : {}").format(cache.instance.size())
        )

    def accept(self, *args, **kwargs):
        # Save keys
        auth.set_app_id_and_api_key(
            self.appIDLineEdit.text(), self.apiKeyLineEdit.text()
        )

        # Save settings
        s = QSettings()
        # warning enabled
        s.setValue(
            "traveltime_platform/warning_enabled", self.warningGroupBox.isChecked()
        )
        # warning limit
        s.setValue("traveltime_platform/warning_limit", self.warningSpinBox.value())
        # logs calls
        s.setValue("traveltime_platform/log_calls", self.logCallsCheckBox.isChecked())
        # disable https
        s.setValue(
            "traveltime_platform/disable_https", self.disableHttpsCheckBox.isChecked()
        )

        super().accept(*args, **kwargs)


class SplashScreen(QDialog):
    def __init__(self, main):
        super().__init__(main.iface.mainWindow())
        uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui", "SplashScreen.ui"), self
        )

        # self.setWindowFlag(Qt.WindowStaysOnTopHint)

        self.buttonBox.accepted.connect(self.accept)

    def showEvent(self, *args, **kwargs):
        super().showEvent(*args, **kwargs)

        # Get the settings
        s = QSettings()
        # warning enabled
        self.dontShowAgainCheckBox.setChecked(
            s.value("traveltime_platform/spashscreen_dontshowagain", False, type=bool)
        )

    def accept(self, *args, **kwargs):
        # Save settings
        s = QSettings()
        # warning enabled
        s.setValue(
            "traveltime_platform/spashscreen_dontshowagain",
            self.dontShowAgainCheckBox.isChecked(),
        )
        super().accept(*args, **kwargs)


class HelpWidget(QWidget):
    def __init__(self, main, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi(os.path.join(os.path.dirname(__file__), "ui", "HelpDialog.ui"), self)

        self.closeButton.pressed.connect(self.close)
        self.openBrowserButton.pressed.connect(self.open_in_browser)
        self.homeButton.pressed.connect(self.reset_url)

        self.main = main

        self.webview = QWebView()
        self.reset_url()

        self.contentWidget.layout().addWidget(self.webview)

    def reset_url(self):
        self.webview.setUrl(
            QUrl(
                "https://igeolise.github.io/traveltime-platform-qgis-plugin/index.html#help-contents"
            )
        )

    def open_in_browser(self):
        webbrowser.open(self.webview.url().toString())
        self.close()


class IsoDateTimeWidgetWrapper(WidgetWrapper):
    def createWidget(self):
        now = QTime.currentTime()
        curdate = QDateTime(QDate.currentDate(), QTime(now.hour(), 0))
        dateEdit = QDateTimeEdit(curdate.toUTC())
        dateEdit.setDisplayFormat("yyyy-MM-dd HH:mm")
        dateEdit.setTimeSpec(Qt.TimeZone)
        return dateEdit

    def setValue(self, value):
        return self.widget.setDateTime(QDateTime().fromString(value, Qt.ISODate))

    def value(self):
        return self.widget.dateTime().toString(Qt.ISODate)

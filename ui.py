import os
import webbrowser
from qgis.PyQt.QtCore import Qt, QSettings, QDateTime, QDate, QTime
from qgis.PyQt.QtWidgets import QDialog, QDateTimeEdit, QWidget
from qgis.PyQt import uic

from processing.gui.AlgorithmDialog import AlgorithmDialog
from processing.gui.wrappers import WidgetWrapper

from . import algorithms
from . import auth
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
            s.value("travel_time_platform/warning_enabled", True, type=bool)
        )
        # warning limit
        self.warningSpinBox.setValue(
            s.value("travel_time_platform/warning_limit", 10, type=int)
        )
        # current count
        self.refresh_count_display()
        # logs calls
        self.logCallsCheckBox.setChecked(
            s.value("travel_time_platform/log_calls", False, type=bool)
        )
        # disable https
        self.disableHttpsCheckBox.setChecked(
            s.value("travel_time_platform/disable_https", False, type=bool)
        )

    def get_key(self):
        webbrowser.open("http://docs.traveltimeplatform.com/overview/getting-keys/")

    def reset_count(self):
        QSettings().setValue("travel_time_platform/current_count", 0)
        self.refresh_count_display()

    def refresh_count_display(self):
        c = QSettings().value("travel_time_platform/current_count", 0, type=int)
        self.countSpinBox.setValue(c)

    def accept(self, *args, **kwargs):
        # Save keys
        auth.set_app_id_and_api_key(
            self.appIDLineEdit.text(), self.apiKeyLineEdit.text()
        )

        # Save settings
        s = QSettings()
        # warning enabled
        s.setValue(
            "travel_time_platform/warning_enabled", self.warningGroupBox.isChecked()
        )
        # warning limit
        s.setValue("travel_time_platform/warning_limit", self.warningSpinBox.value())
        # logs calls
        s.setValue("travel_time_platform/log_calls", self.logCallsCheckBox.isChecked())
        # disable https
        s.setValue(
            "travel_time_platform/disable_https", self.disableHttpsCheckBox.isChecked()
        )

        super().accept(*args, **kwargs)


class SplashScreen(QDialog):
    def __init__(self, main):
        super().__init__(main.iface.mainWindow())
        uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui", "SplashScreen.ui"), self
        )

        # self.setWindowFlag(Qt.WindowStaysOnTopHint)

        self.main = main

        # Load html files
        html_path = os.path.join(HELP_DIR, "{tab}.{locale}.html")
        locale = QSettings().value("locale/userLocale")[0:2]

        css_path = os.path.join(HELP_DIR, "help.css")
        css = open(css_path).read()

        for tab_key, tab_name in [
            ("01.about", tr("About")),
            ("02.apikey", tr("API key")),
            ("03.start", tr("Getting started")),
            ("04.simplified", tr("TimeMap - Simplified")),
            ("05.advanced", tr("TimeMap - Advanced")),
            ("06.issues", tr("Troubleshooting")),
        ]:

            path = html_path.format(tab=tab_key, locale=locale)
            if not os.path.isfile(path):
                path = html_path.format(tab=tab_key, locale="en")

            body = open(path, "r").read()
            html = "<html><head><style>{css}</style></head><body>{body}</body></html>".format(
                css=css, body=body
            )
            page = HelpWidget(self.main, html)

            self.tabWidget.addTab(page, tab_name)

        self.buttonBox.accepted.connect(self.accept)

    def showEvent(self, *args, **kwargs):
        super().showEvent(*args, **kwargs)

        # Get the settings
        s = QSettings()
        # warning enabled
        self.dontShowAgainCheckBox.setChecked(
            s.value("travel_time_platform/spashscreen_dontshowagain", False, type=bool)
        )

    def accept(self, *args, **kwargs):
        # Save settings
        s = QSettings()
        # warning enabled
        s.setValue(
            "travel_time_platform/spashscreen_dontshowagain",
            self.dontShowAgainCheckBox.isChecked(),
        )
        super().accept(*args, **kwargs)


class HelpWidget(QWidget):
    def __init__(self, main, html, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui", "HelpContent.ui"), self
        )

        self.main = main
        self.htmlWidget.anchorClicked.connect(self.open_link)
        self.htmlWidget.setText(html)
        self.htmlWidget.setSearchPaths([HELP_DIR])

    def open_link(self, url):

        # self.main.splash_screen.hide()

        if url.url() == "#show_config":
            self.main.show_config()
        elif url.url() == "#show_toolbox":
            self.main.show_toolbox()
        elif url.url() == "#run_simple":
            # See https://github.com/qgis/QGIS/blob/final-3_6_1/python/plugins/processing/gui/ProcessingToolbox.py#L240-L270
            alg = algorithms.TimeMapSimpleAlgorithm().create()
            dlg = alg.createCustomParametersWidget(self.main.iface.mainWindow())
            if not dlg:
                dlg = AlgorithmDialog(alg, False, self.main.iface.mainWindow())
            dlg.show()
            dlg.exec_()
        elif url.url()[0:4] == "http":
            webbrowser.open(url.url())
        else:
            log("Unknown url : {}".format(url.url()), "TimeTravelPlatform")


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

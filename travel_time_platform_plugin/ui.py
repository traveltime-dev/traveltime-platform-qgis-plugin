import os
import webbrowser

from processing.gui.AlgorithmDialog import AlgorithmDialog
from processing.gui.ParametersPanel import ParametersPanel
from qgis.gui import QgsAbstractProcessingParameterWidgetWrapper as Wrapper
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDate, QDateTime, QSettings, Qt, QTime, QUrl
from qgis.PyQt.QtWidgets import QDateTimeEdit, QDialog, QWidget

try:
    from qgis.PyQt.QtWebKitWidgets import QWebView

    webkit_available = True
except (ModuleNotFoundError, ImportError):
    webkit_available = False

from processing.gui.wrappers import WidgetWrapper

from . import auth, cache, constants
from .utils import tr

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
        self.endpointResetButton.pressed.connect(self.reset_endpoint)
        self.apiKeyHelpLabel.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.apiKeyHelpLabel.setOpenExternalLinks(True)
        self.throttleCallsCheckBox.toggled.connect(self.throttleCallsSpinBox.setEnabled)

    def showEvent(self, *args, **kwargs):
        super().showEvent(*args, **kwargs)

        # Get the current keys
        app_id, api_key = auth.get_app_id_and_api_key()

        self.appIDLineEdit.setText(app_id)
        self.apiKeyLineEdit.setText(api_key)

        # Get the settings
        s = QSettings()
        # current count
        self.refresh_count_display()
        # endpoint
        self.refresh_endpoint_display()
        # logs calls
        self.logCallsCheckBox.setChecked(
            s.value("traveltime_platform/log_calls", False, type=bool)
        )
        # show tests button
        self.showRunTestsButton.setChecked(
            s.value("traveltime_platform/show_tests_button", False, type=bool)
        )
        # disable https
        self.disableHttpsCheckBox.setChecked(
            s.value("traveltime_platform/disable_https", False, type=bool)
        )
        # throttling
        self.throttleCallsCheckBox.setChecked(
            s.value("traveltime_platform/throttling_enabled", False, type=bool)
        )
        self.throttleCallsSpinBox.setValue(
            s.value("traveltime_platform/throttling_max_searches_count", 300, type=int)
        )
        # refresh current cache
        self.refresh_cache_label()

    def get_key(self):
        webbrowser.open("https://docs.traveltime.com/qgis/sign-up/")

    def reset_count(self):
        QSettings().setValue("traveltime_platform/current_count", 0)
        self.refresh_count_display()

    def refresh_count_display(self):
        c = QSettings().value("traveltime_platform/current_count", 0, type=int)
        self.countSpinBox.setValue(c)

    def reset_endpoint(self):
        QSettings().remove("traveltime_platform/custom_endpoint")
        self.refresh_endpoint_display()

    def refresh_endpoint_display(self):
        e = QSettings().value(
            "traveltime_platform/custom_endpoint", constants.DEFAULT_ENDPOINT, type=str
        )
        self.endpointLineEdit.setText(e)

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
        # logs calls
        s.setValue("traveltime_platform/log_calls", self.logCallsCheckBox.isChecked())
        # show tests button
        s.setValue(
            "traveltime_platform/show_tests_button", self.showRunTestsButton.isChecked()
        )
        # disable https
        s.setValue(
            "traveltime_platform/disable_https", self.disableHttpsCheckBox.isChecked()
        )
        # throttling
        s.setValue(
            "traveltime_platform/throttling_enabled",
            self.throttleCallsCheckBox.isChecked(),
        )
        s.setValue(
            "traveltime_platform/throttling_max_searches_count",
            self.throttleCallsSpinBox.value(),
        )
        # endpoint
        s.setValue("traveltime_platform/custom_endpoint", self.endpointLineEdit.text())

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
    home = "https://hubs.ly/H0rnCjY0"

    def __init__(self, main, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi(os.path.join(os.path.dirname(__file__), "ui", "HelpDialog.ui"), self)

        self.closeButton.pressed.connect(self.close)
        self.openBrowserButton.pressed.connect(self.open_in_browser)
        self.homeButton.pressed.connect(self.reset_url)

        self.main = main

        if webkit_available:
            self.webview = QWebView()
            self.reset_url()
            self.contentWidget.layout().addWidget(self.webview)
        else:
            self.webview = None

    def show(self):
        if self.webview:
            self.raise_()
            super().show()
        else:
            webbrowser.open(self.home)

    def reset_url(self):
        self.webview.setUrl(QUrl(self.home))

    def open_in_browser(self):
        webbrowser.open(self.webview.url().toString())
        self.close()


class IsoDateTimeWidgetWrapper(WidgetWrapper):
    def createWidget(self):
        now = QTime.currentTime()
        curdate = QDateTime(QDate.currentDate(), QTime(now.hour(), 0))
        dateEdit = QDateTimeEdit(curdate)
        dateEdit.setDisplayFormat("yyyy-MM-dd HH:mm")
        return dateEdit

    def setValue(self, value):
        return self.widget.setDateTime(QDateTime().fromString(value, Qt.ISODate))

    def value(self):
        return self.widget.dateTime().toString(Qt.ISODate)


class AlgorithmDialogWithSkipLogic(AlgorithmDialog):
    def getParametersPanel(self, alg, parent):
        panel = ParametersPanel(parent, alg, self.in_place, self.active_layer)
        skip_logic = self.algorithm().skip_logic

        # callable that toggles visibility of a field's widget depending on another field
        def toggler(wrapper: Wrapper, depends_on: Wrapper):
            truthy = bool(depends_on.widgetValue())
            wrapper.wrappedLabel().setVisible(truthy)
            wrapper.wrappedWidget().setVisible(truthy)

        # callable that toggles all the fields for initialisation
        def toggle_all():
            for field_name, wrapper in panel.wrappers.items():
                depends_on_name = skip_logic.get(field_name, None)
                if not depends_on_name:
                    continue
                depends_on = panel.wrappers[depends_on_name]
                toggler(wrapper, depends_on=depends_on)

        # connect signals on source fields for skip logic
        for field_name, wrapper in panel.wrappers.items():
            depends_on_name = skip_logic[field_name]
            if not depends_on_name:
                continue
            depends_on = panel.wrappers[depends_on_name]
            depends_on.widgetValueHasChanged.connect(
                lambda depends_on, wrapper=wrapper: toggler(
                    wrapper, depends_on=depends_on
                )
            )

        # toggling groupbox resets it's children visibility, so we reinitialise it
        advanced_groupbox = panel.findChild(QWidget, "grpAdvanced")
        advanced_groupbox.collapsedStateChanged.connect(lambda _: toggle_all())

        # initialise for opening state
        toggle_all()

        return panel

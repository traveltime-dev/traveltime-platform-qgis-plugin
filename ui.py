import os
import webbrowser
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt import uic

from . import auth
from .utils import tr


class ConfigDialog(QDialog):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'ui', 'ConfigDialog.ui'), self)

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
        self.warningGroupBox.setChecked(s.value('travel_time_platform/warning_enabled', True, type=bool))
        # warning limit
        self.warningSpinBox.setValue(s.value('travel_time_platform/warning_limit', 10, type=int))
        # current count
        self.refresh_count_display()
        # logs calls
        self.logCallsCheckBox.setChecked(s.value('travel_time_platform/log_calls', False, type=bool))

    def get_key(self):
        webbrowser.open('http://docs.traveltimeplatform.com/overview/getting-keys/')

    def reset_count(self):
        QSettings().setValue('travel_time_platform/current_count', 0)
        self.refresh_count_display()

    def refresh_count_display(self):
        c = QSettings().value('travel_time_platform/current_count', 0, type=int)
        self.countSpinBox.setValue(c)

    def accept(self, *args, **kwargs):
        # Save keys
        auth.set_app_id_and_api_key(self.appIDLineEdit.text(), self.apiKeyLineEdit.text())

        # Save settings
        s = QSettings()
        # warning enabled
        s.setValue('travel_time_platform/warning_enabled', self.warningGroupBox.isChecked())
        # warning limit
        s.setValue('travel_time_platform/warning_limit', self.warningSpinBox.value())
        # logs calls
        s.setValue('travel_time_platform/log_calls', self.logCallsCheckBox.isChecked())

        super().accept(*args, **kwargs)


class SplashScreen(QDialog):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'ui', 'SplashScreen.ui'), self)

        self.buttonBox.accepted.connect(self.accept)
        self.clickableText.linkActivated.connect(self.open_link)

    def showEvent(self, *args, **kwargs):
        super().showEvent(*args, **kwargs)

        # Get the settings
        s = QSettings()
        # warning enabled
        self.dontShowAgainCheckBox.setChecked(s.value('travel_time_platform/spashscreen_dontshowagain', False, type=bool))

    def open_link(self, link):
        webbrowser.open(link)

    def accept(self, *args, **kwargs):
        # Save settings
        s = QSettings()
        # warning enabled
        s.setValue('travel_time_platform/spashscreen_dontshowagain', self.dontShowAgainCheckBox.isChecked())
        super().accept(*args, **kwargs)

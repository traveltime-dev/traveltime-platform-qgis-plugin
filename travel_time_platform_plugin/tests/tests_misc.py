import requests
from processing import createAlgorithmDialog
from qgis.core import Qgis, QgsPointXY, QgsProcessingContext, QgsProject
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QApplication, QDockWidget, QTreeView, QWidget
from qgis.utils import iface

from .. import cache
from ..constants import CREDENTIAL_HEADERS
from ..utils import log
from .base import TestCaseBase


class MiscTest(TestCaseBase):
    """Testing other features"""

    def test_loading_map_tiles(self):
        browser = iface.mainWindow().findChild(QDockWidget, "Browser")
        treeview = browser.findChild(QTreeView)
        model = treeview.model()

        # Hide the browser
        browser.setVisible(False)
        # Select the first item
        treeview.setCurrentIndex(model.index(0, 0))

        self._feedback()

        # Ensure the browser is hidden
        self.assertFalse(browser.isVisible())
        # Ensure the XYZ layer is not selected
        self.assertNotEqual(
            model.data(treeview.currentIndex()),
            "TravelTime - Lux",
        )

        # Use the action
        self.plugin.action_show_tiles.trigger()
        self._feedback()

        # Ensure the panel got shown
        self.assertTrue(browser.isVisible())
        # Ensure the XYZ layer got selected
        self.assertEqual(
            model.data(treeview.currentIndex()),
            "TravelTime - Lux",
        )

    def test_cache_omits_credentials(self):
        # lower case too: headers are matched case-insensitively over the wire
        for spelling in (str.title, str.lower):
            with self.subTest(spelling=spelling.__name__):
                request = requests.Request(
                    "POST",
                    "https://api.traveltimeapp.com/v4/time-map",
                    headers={
                        "Accept": "application/json",
                        **{spelling(h): f"secret-{h}" for h in CREDENTIAL_HEADERS},
                    },
                ).prepare()
                response = requests.Response()
                response.status_code = 200
                response._content = b"{}"
                response.request = request

                reduced = cache.instance.cached_requests.cache.reduce_response(response)

                for header in CREDENTIAL_HEADERS:
                    self.assertNotIn(header, reduced.request.headers)
                    # the live request must keep them, or the call itself would fail
                    self.assertIn(header, request.headers)
                self.assertEqual(reduced.request.headers["Accept"], "application/json")

    def test_express_reports_api_error(self):
        settings = QSettings()
        endpoint_key = "traveltime_platform/custom_endpoint"
        previous_endpoint = settings.value(endpoint_key)
        settings.setValue(endpoint_key, "http://127.0.0.1:1")
        try:
            self.plugin.express_time_map_action.trigger()
            self._feedback()
            self._click(QgsPointXY(-0.13, 51.5))
        finally:
            if previous_endpoint is None:
                settings.remove(endpoint_key)
            else:
                settings.setValue(endpoint_key, previous_endpoint)

        # The failure must reach the message bar rather than escaping the tool
        item = iface.messageBar().currentItem()
        self.assertIsNotNone(item)
        self.assertEqual(item.title(), "Error")
        self.assertEqual(item.level(), Qgis.MessageLevel.Critical)
        self.assertEqual(QgsProject.instance().mapLayersByName("Output"), [])

    def test_skip_logic(self):
        dialog = createAlgorithmDialog("ttp_v4:time_map", {})
        params_widget = dialog.mainWidget()
        advanced_groupbox = params_widget.findChild(QWidget, "grpAdvanced")

        def assert_visibility(field_name: str, expected_visibility: bool):
            label = params_widget.wrappers[field_name].wrappedLabel()
            widget = params_widget.wrappers[field_name].wrappedWidget()
            self.assertEqual(label.isVisibleTo(dialog), expected_visibility)
            self.assertEqual(widget.isVisibleTo(dialog), expected_visibility)

        def set_value(field_name: str, value: str):
            wrapper = params_widget.wrappers[field_name]
            log(f"Value was {wrapper.widgetValue()}")
            wrapper.setWidgetValue(value, QgsProcessingContext())
            QApplication.processEvents()

        def toggle_advanced():
            advanced_groupbox.toggleCollapsed()
            QApplication.processEvents()

        # show the dialog
        dialog.show()

        # initially, dependent fields should be hidden
        assert_visibility("INPUT_DEPARTURE_ID", False)
        assert_visibility("INPUT_DEPARTURE_EXISTING_FIELDS_TO_KEEP", False)

        # close and reopen advanced groupbox
        toggle_advanced()
        toggle_advanced()

        # this should have no effect
        assert_visibility("INPUT_DEPARTURE_ID", False)
        assert_visibility("INPUT_DEPARTURE_EXISTING_FIELDS_TO_KEEP", False)

        # we set a value for departure searches
        set_value("INPUT_DEPARTURE_SEARCHES", "something")

        # dependent fields should now be visible
        assert_visibility("INPUT_DEPARTURE_ID", True)
        assert_visibility("INPUT_DEPARTURE_EXISTING_FIELDS_TO_KEEP", True)

        # close and reopen advanced groupbox
        toggle_advanced()
        toggle_advanced()

        # this should have no effect
        assert_visibility("INPUT_DEPARTURE_ID", True)
        assert_visibility("INPUT_DEPARTURE_EXISTING_FIELDS_TO_KEEP", True)

        # FIXME: setting an empty value has no effect, and couldn't find a workaround, meaning we stop the test here
        # unset a value for departure searches
        # set_value("INPUT_DEPARTURE_SEARCHES", "")

        # dependent fields should be hidden again
        # assert_visibility("INPUT_DEPARTURE_ID", False)
        # assert_visibility("INPUT_DEPARTURE_EXISTING_FIELDS_TO_KEEP", False)

        # close and reopen advanced groupbox
        # toggle_advanced()
        # toggle_advanced()

        # this should have no effect
        # assert_visibility("INPUT_DEPARTURE_ID", False)
        # assert_visibility("INPUT_DEPARTURE_EXISTING_FIELDS_TO_KEEP", False)

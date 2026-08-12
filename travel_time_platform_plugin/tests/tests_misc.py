import pickle

import processing
import requests
from processing import createAlgorithmDialog
from qgis.core import (
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProject,
    QgsSettings,
)
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QApplication, QDockWidget, QTreeView, QWidget
from qgis.utils import iface

from .. import auth, cache
from ..algorithms import base
from ..constants import CREDENTIAL_HEADERS
from ..utils import log
from .base import TestCaseBase


class _CollectingFeedback(QgsProcessingFeedback):
    """Keeps what the algorithm reported, which run() otherwise only logs"""

    def __init__(self):
        super().__init__()
        self.errors = []

    def reportError(self, error, fatalError=False):
        self.errors.append(error)


class MiscTest(TestCaseBase):
    """Testing other features"""

    def test_loading_map_tiles(self):
        browser = iface.mainWindow().findChild(QDockWidget, "Browser")
        treeview = browser.findChild(QTreeView)
        model = treeview.model()
        expected_label = self.plugin.tilesManager.default_browser_label()

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
            expected_label,
        )

        # Use the action
        self.plugin.action_show_tiles.trigger()
        self._feedback()

        # Ensure the panel got shown
        self.assertTrue(browser.isVisible())
        # Ensure the XYZ layer got selected
        self.assertEqual(
            model.data(treeview.currentIndex()),
            expected_label,
        )

    def test_tiles_drops_retired_entries(self):
        tiles_manager = self.plugin.tilesManager
        settings = QgsSettings()
        retired = "connections/xyz/items/TravelTime - Lux"
        settings.setValue(
            f"{retired}/url", "https://tiles.traveltime.com/lux/1/2/3.png"
        )

        tiles_manager.add_tiles_to_browser()

        # An upgrade must not leave the old style behind in the browser
        self.assertIsNone(settings.value(f"{retired}/url"))
        for identifier in tiles_manager.tiles:
            label = tiles_manager.browser_label(identifier)
            self.assertIsNotNone(
                settings.value(f"connections/xyz/items/{label}/url"), label
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

                # what reaches the file is the pickle, not just this one field
                pickled = pickle.dumps(reduced)
                for header in CREDENTIAL_HEADERS:
                    self.assertNotIn(header, reduced.request.headers)
                    self.assertNotIn(f"secret-{header}".encode(), pickled)
                    # the live request must keep them, or the call itself would fail
                    self.assertIn(header, request.headers)
                self.assertEqual(reduced.request.headers["Accept"], "application/json")

    def test_gateway_error_is_reported(self):
        # A gateway in front of the API answers with a body the plugin does not expect
        for body in (b'{"message":"upstream"}', b"[]"):
            with self.subTest(body=body):
                response = requests.Response()
                response.status_code = 502
                response.reason = "Bad Gateway"
                response.url = "https://api.traveltimeapp.com/v4/time-map"
                response._content = body
                response.from_cache = False

                session = cache.instance.cached_requests
                original_send = session.send
                session.send = lambda request, **kwargs: response
                feedback = _CollectingFeedback()
                try:
                    with self.assertRaises(QgsProcessingException):
                        processing.run(
                            "ttp_v4:time_map",
                            {
                                "INPUT_DEPARTURE_SEARCHES": self._make_layer(
                                    ["POINT(0.0 51.5)"]
                                ).id(),
                                "INPUT_DEPARTURE_TIME": self._today_at_noon().isoformat(),
                                "INPUT_DEPARTURE_TRAVEL_TIME": "900",
                                "OUTPUT": "memory:",
                            },
                            feedback=feedback,
                        )
                finally:
                    session.send = original_send

                # The status must reach the user rather than a KeyError or TypeError
                joined = "\n".join(feedback.errors)
                self.assertIn("502", joined)
                self.assertIn("Bad Gateway", joined)

    def test_log_calls_redacts_credentials(self):
        settings = QSettings()
        keys = {
            "traveltime_platform/log_calls": True,
            "traveltime_platform/custom_endpoint": "http://127.0.0.1:1",
        }
        previous = {k: settings.value(k) for k in keys}
        for key, value in keys.items():
            settings.setValue(key, value)

        messages = []
        original_log = base.log
        base.log = lambda msg, *args, **kwargs: messages.append(str(msg))
        try:
            self.plugin.express_time_map_action.trigger()
            self._feedback()
            self._click(QgsPointXY(-0.13, 51.5))
        finally:
            base.log = original_log
            for key, value in previous.items():
                if value is None:
                    settings.remove(key)
                else:
                    settings.setValue(key, value)

        joined = "\n".join(messages)
        self.assertIn("*hidden*", joined)
        for secret in auth.get_app_id_and_api_key():
            self.assertNotIn(secret, joined)

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

        item = iface.messageBar().currentItem()
        self.assertEqual(item.title(), "Error")
        # an empty critical bubble is the failure this guards against
        self.assertIn("Error while connecting to the API", item.text())
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

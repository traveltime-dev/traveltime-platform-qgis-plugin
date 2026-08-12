import os
import pickle
import shutil
import tempfile

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

from .. import auth, cache, tiles
from ..algorithms import base
from ..constants import CREDENTIAL_HEADERS
from ..libraries.requests_cache.backends import DbCache
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

    def _legacy_cache_entry(self):
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.request = requests.Request(
            "POST",
            "https://api.traveltimeapp.com/v4/time-map",
            headers={"X-Api-Key": "secret-legacy-key"},
        ).prepare()
        return response

    def _make_sibling_cache_dir(self):
        """A stand-in for the other QGIS generation, wherever this platform puts it"""
        generations, relative = cache.instance._generations_root()
        sibling_dir = tempfile.mkdtemp(dir=generations)
        sibling = os.path.join(sibling_dir, relative)
        os.makedirs(os.path.dirname(sibling), exist_ok=True)
        return sibling_dir, sibling

    def test_cache_finds_the_other_generations_file(self):
        sibling_dir, sibling = self._make_sibling_cache_dir()
        try:
            open(sibling, "wb").close()
            self.assertIn(sibling, cache.instance._sibling_cache_paths())
            self.assertNotIn(cache.instance.path, cache.instance._sibling_cache_paths())
        finally:
            shutil.rmtree(sibling_dir, ignore_errors=True)

    def test_cache_purges_once(self):
        backend = cache.instance.cached_requests.cache
        settings = QSettings()
        sibling_dir, sibling = self._make_sibling_cache_dir()
        other = DbCache(os.path.splitext(sibling)[0])
        # only the synthetic one: a real other generation may be running
        original_siblings = cache.instance._sibling_cache_paths
        cache.instance._sibling_cache_paths = lambda: [sibling]
        try:
            other.save_response("legacy-key", self._legacy_cache_entry())
            backend.save_response("legacy-key", self._legacy_cache_entry())
            settings.remove(cache.PURGED_SETTING)
            settings.remove(cache.SIBLINGS_PURGED_SETTING)
            cache.instance._purge_credentials_once()

            self.assertFalse(backend.has_key("legacy-key"))
            # the other generation loses its entries but keeps usable tables,
            # or its running QGIS would raise on every request from then on
            self.assertFalse(other.has_key("legacy-key"))
            with open(sibling, "rb") as f:
                self.assertNotIn(b"secret-legacy-key", f.read())
            self.assertTrue(settings.value(cache.PURGED_SETTING, False, type=bool))

            # having run once, it must not wipe a healthy cache on every start
            backend.save_response("kept-key", self._legacy_cache_entry())
            cache.instance._purge_credentials_once()
            self.assertTrue(backend.has_key("kept-key"))

            # a failed purge must stay pending rather than report success
            settings.remove(cache.PURGED_SETTING)
            original_clear = cache.instance.clear
            cache.instance.clear = lambda: (_ for _ in ()).throw(OSError("locked"))
            try:
                cache.instance._purge_credentials_once()
            finally:
                cache.instance.clear = original_clear
            self.assertFalse(settings.value(cache.PURGED_SETTING, False, type=bool))

            # a sibling we cannot clear — one another QGIS holds open — must be
            # retried, not recorded as done
            settings.remove(cache.SIBLINGS_PURGED_SETTING)
            unclearable = os.path.join(sibling_dir, "not-a-database.sqlite")
            with open(unclearable, "wb") as f:
                f.write(b"definitely not sqlite")
            cache.instance._sibling_cache_paths = lambda: [unclearable]
            cache.instance._purge_credentials_once()
            self.assertFalse(
                settings.value(cache.SIBLINGS_PURGED_SETTING, False, type=bool)
            )
        finally:
            cache.instance._sibling_cache_paths = original_siblings
            settings.setValue(cache.PURGED_SETTING, True)
            settings.setValue(cache.SIBLINGS_PURGED_SETTING, True)
            shutil.rmtree(sibling_dir, ignore_errors=True)

    def test_tiles_keeps_live_entries_when_probe_fails(self):
        tiles_manager = self.plugin.tilesManager
        settings = QgsSettings()
        items = "connections/xyz/items"
        mine = f"{items}/TravelTime - Mine"
        retired = f"{items}/TravelTime - Lux"
        current = tiles_manager.default_browser_label()

        cases = {
            "unreachable": lambda *a, **kw: (_ for _ in ()).throw(OSError("refused")),
            "blocked": lambda *a, **kw: self._html_response(),
        }
        for name, fake_get in cases.items():
            with self.subTest(probe=name):
                settings.setValue(
                    f"{retired}/url", "https://tiles.traveltime.com/lux/1/2/3.png"
                )
                settings.setValue(f"{mine}/url", "https://example.com/{z}/{x}/{y}.png")
                original_get = tiles.requests.get
                tiles.requests.get = fake_get
                try:
                    self.assertFalse(tiles_manager.add_tiles_to_browser())
                    self.assertIsNone(settings.value(f"{retired}/url"))
                    # the user may have kept an entry of their own under the prefix
                    self.assertIsNotNone(settings.value(f"{mine}/url"))
                finally:
                    tiles.requests.get = original_get
                    settings.remove(mine)

        # a failed probe must not have cost the user their working entries
        tiles_manager.add_tiles_to_browser()
        self.assertIsNotNone(settings.value(f"{items}/{current}/url"))

    def _html_response(self):
        response = requests.Response()
        response.status_code = 200
        response._content = b"<html>blocked"
        return response

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

from processing import createAlgorithmDialog
from qgis.core import QgsProcessingContext
from qgis.PyQt.QtWidgets import QApplication, QDockWidget, QTreeView, QWidget
from qgis.utils import iface

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

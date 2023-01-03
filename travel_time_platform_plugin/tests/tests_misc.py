from qgis.PyQt.QtWidgets import QDockWidget, QTreeView
from qgis.utils import iface

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

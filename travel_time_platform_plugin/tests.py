import os
from datetime import datetime
from itertools import product
from pathlib import Path
from tempfile import gettempdir

from qgis.core import (
    QgsApplication,
    QgsBrightnessContrastFilter,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsHueSaturationFilter,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.gui import QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QPoint, Qt
from qgis.PyQt.QtGui import QPixmap
from qgis.testing import unittest
from qgis.utils import iface, plugins

from travel_time_platform_plugin import auth
from travel_time_platform_plugin.main import TTPPlugin

TEST_MODE = os.environ.get("TEST_MODE", "DESKTOP")  # HEADLESS | HEADFULL | DESKTOP
assert TEST_MODE in ["HEADLESS", "HEADFULL", "DESKTOP"]


class TestCaseBase(unittest.TestCase):
    def setUp(self):
        self.__feedback_step = 0
        self.plugin: TTPPlugin = plugins["travel_time_platform_plugin"]

        # Unless we're in desktop (where we use the existing config), we must setup API keys from env vars
        if TEST_MODE != "DESKTOP":
            # Hardcode a master password and set API credentials
            QgsApplication.instance().authManager().setMasterPassword("testing")
            auth.set_app_id_and_api_key(
                os.environ.get("API_APP_ID"), os.environ.get("API_KEY")
            )

        # If visual, add a background layer
        rl = QgsRasterLayer(
            f"type=xyz&url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19&zmin=0&http-header:referer=",
            "OpenStreetMap",
            "wms",
        )
        desaturate = QgsHueSaturationFilter()
        desaturate.setSaturation(-90)
        rl.pipe().set(desaturate)
        darken = QgsBrightnessContrastFilter()
        darken.setBrightness(-20)
        darken.setContrast(-20)
        rl.pipe().set(darken)
        QgsProject.instance().addMapLayer(rl)
        QgsApplication.processEvents()

        # Configure the project
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem(4326))
        iface.mapCanvas().setCenter(QgsPointXY(-0.13, 51.50))
        iface.mapCanvas().zoomScale(20000)

        # ready
        self._feedback("starting")

    def tearDown(self):
        self._feedback("finished")
        QgsProject.instance().setDirty(False)
        iface.messageBar().clearWidgets()
        iface.newProject()

    def _feedback(self, message=None, seconds=1):
        """Waits a little so we can see what happens when running the tests with GUI"""

        self.__feedback_step += 1
        if message:
            iface.messageBar().clearWidgets()
            iface.messageBar().pushMessage(
                "Info",
                f"Test `{self._testMethodName}`: {message}",
                duration=0,
            )

        if TEST_MODE != "HEADLESS":
            t = datetime.now()
            while (datetime.now() - t).total_seconds() < seconds:
                QgsApplication.processEvents()
        QgsApplication.processEvents()

        # Save artifacts
        artifact_name = f"{self.__class__.__name__}-{self._testMethodName}-{self.__feedback_step:03}"
        artifacts_dir = Path(gettempdir()) / "ttp_tests" / f"{artifact_name}.jpg"
        os.makedirs(artifacts_dir.parent, exist_ok=True)
        rect = iface.mainWindow().size()
        pixmap = QPixmap(rect)
        iface.mainWindow().render(pixmap)
        pixmap.save(str(artifacts_dir))

    def _make_layer(
        self, wkt_geoms, layer_type="point?crs=epsg:4326"
    ) -> QgsVectorLayer:
        """Helper that adds a styled vector layer with the given geometries to the project and returns it"""
        vl = QgsVectorLayer(layer_type, "temp", "memory")
        for wkt_geom in wkt_geoms:
            feat = QgsFeature()
            feat.setGeometry(QgsGeometry.fromWkt(wkt_geom))
            vl.dataProvider().addFeature(feat)
        QgsProject.instance().addMapLayer(vl)
        return vl

    def _click(self, map_pos: QgsPointXY):
        canvas = iface.mapCanvas()

        # Pan to click
        canvas.setCenter(map_pos)

        # Retrieve pixel position
        device_pos = canvas.getCoordinateTransform().transform(map_pos)
        pixel = QPoint(int(device_pos.x()), int(device_pos.y()))

        # debug
        print(f"Clicking at {pixel} in canvas {canvas.size()}")

        canvas.setFocus()

        # Do the click
        tool = canvas.mapTool()
        tool.canvasMoveEvent(
            QgsMapMouseEvent(canvas, QEvent.MouseMove, pixel, Qt.NoButton)
        )
        tool.canvasPressEvent(
            QgsMapMouseEvent(canvas, QEvent.MouseButtonPress, pixel, Qt.LeftButton)
        )
        tool.canvasReleaseEvent(
            QgsMapMouseEvent(canvas, QEvent.MouseButtonRelease, pixel, Qt.LeftButton)
        )

        self._feedback()


class ExpressToolsTest(TestCaseBase):
    def test_express_time_map_action(self):

        # Use the action
        self.plugin.express_time_map_action.trigger()
        self._feedback()
        self._click(QgsPointXY(-0.13, 51.5))

        # Ensure we got exactly one output
        output_layers = QgsProject.instance().mapLayersByName("Output")
        self.assertEqual(len(output_layers), 1)

        # Ensure the output got exactly one feature
        output_layer = output_layers[0]
        self.assertEqual(output_layer.featureCount(), 1)

    def test_express_time_filter_action(self):

        # Create a data layer
        vl = self._make_layer(
            [
                f"POINT({-0.13+x/100} {51.50+y/100})"
                for x, y in product(range(-5, 5), range(-5, 5))
            ]
        )
        iface.setActiveLayer(vl)

        # Use the action
        self.plugin.express_time_filter_action.trigger()
        self._click(QgsPointXY(-0.13, 51.5))

        # Ensure we got exactly one output
        output_layers = QgsProject.instance().mapLayersByName("Output")
        self.assertEqual(len(output_layers), 1)

        # Ensure the output got some features
        output_layer = output_layers[0]
        self.assertGreater(output_layer.featureCount(), 0)

    def test_express_route_action(self):

        # Configure the time
        self.plugin.express_route_action.menu.show()
        self._feedback()
        self.plugin.express_route_action.widget.dateTimeEdit.setDateTime(
            datetime.now().replace(hour=12, minute=30, second=0)
        )
        self._feedback()
        self.plugin.express_route_action.menu.hide()

        # Use the action
        self.plugin.express_route_action.trigger()
        self._feedback()
        self._click(QgsPointXY(-0.1253, 51.5084))
        self._click(QgsPointXY(-0.1238, 51.5306))

        # Ensure we got exactly one output
        output_layers = QgsProject.instance().mapLayersByName("Output")
        self.assertEqual(len(output_layers), 1)

        # Ensure the output got some features
        output_layer = output_layers[0]
        self.assertGreater(output_layer.featureCount(), 0)

    def test_geoclick(self):

        # Configure the time
        self.plugin.express_geoclick_lineedit.setText("London")
        self.plugin.express_geoclick_action.trigger()
        self._feedback()
        self.assertLess(
            QgsPointXY(-0.1276, 51.5072).distance(iface.mapCanvas().center()), 0.1
        )

        self.plugin.express_geoclick_lineedit.setText("Edinburgh")
        self.plugin.express_geoclick_action.trigger()
        self._feedback()
        self.assertLess(
            QgsPointXY(-3.1883, 55.9533).distance(iface.mapCanvas().center()), 0.1
        )

        self.plugin.express_geoclick_lineedit.setText("Glasgow")
        self.plugin.express_geoclick_action.trigger()
        self._feedback()
        self.assertLess(
            QgsPointXY(-4.2518, 55.8642).distance(iface.mapCanvas().center()), 0.1
        )


if __name__ == "__console__":
    # Run from within QGIS console
    unittest.main(ExpressToolsTest(), exit=False)

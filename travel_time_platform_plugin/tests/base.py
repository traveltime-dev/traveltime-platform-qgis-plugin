import os
from datetime import datetime
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

from .. import auth
from ..main import TTPPlugin

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

        # Show which test is running
        iface.messageBar().clearWidgets()
        iface.messageBar().pushMessage(
            "Info",
            f"Running test `{self._testMethodName}`",
            duration=0,
        )

        # ready
        self._feedback()

    def tearDown(self):
        self._feedback()
        QgsProject.instance().setDirty(False)
        iface.messageBar().clearWidgets()
        iface.newProject()

    def _feedback(self, seconds=1):
        """Waits a little so we can see what happens when running the tests with GUI"""

        self.__feedback_step += 1

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

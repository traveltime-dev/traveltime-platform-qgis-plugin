import os
from functools import partial
from qgis.PyQt.QtCore import Qt, QDateTime, QEvent, QPoint
from qgis.PyQt.QtWidgets import (
    QAction,
    QWidget,
    QWidgetAction,
    QMenu,
    QVBoxLayout,
    QPushButton,
)

from qgis.core import (
    QgsApplication,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingAlgRunnerTask,
    QgsProcessingException,
    Qgis,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsProcessingFeedback,
    QgsFeatureRequest,
    QgsWkbTypes,
    QgsMapLayer,
    QgsPointXY,
)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker
from qgis.PyQt import uic

import processing

from .utils import tr, log
from . import resources


def pointToLayer(coords):
    """Returns a layer usable by processing from a QgsPoint"""

    layer = QgsVectorLayer(
        "Point?crs={}".format(QgsProject.instance().crs().authid()),
        "temporary_points",
        "memory",
    )
    fet = QgsFeature()
    fet.setGeometry(QgsGeometry.fromPointXY(coords))
    layer.dataProvider().addFeatures([fet])

    return layer


class ExpressActionBase(QAction):
    _icon = None  # to be defined by subclasses
    _name = None  # to be defined by subclasses
    _widget_ui = None  # to be defined by subclasses
    _algorithm = None  # to be defined by subclasses

    def __init__(self, main):
        super().__init__(self._icon, self._name)
        self.setCheckable(True)

        self.main = main

        # Build the widget
        self.widget = QWidget()
        uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui", self._widget_ui), self.widget
        )
        self.widget.dateTimeEdit.setDateTime(QDateTime.currentDateTime())

        self.widgetAction = QWidgetAction(self)
        self.widgetAction.setDefaultWidget(self.widget)

        self.menu = QMenu()
        self.menu.addAction(self.widgetAction)
        self.setMenu(self.menu)

        # Build the tool
        self.tool = QgsMapToolEmitPoint(self.main.iface.mapCanvas())
        self.tool.activated.connect(lambda: self.setChecked(True))
        self.tool.deactivated.connect(lambda: self.setChecked(False))
        self.tool.canvasClicked.connect(self.tool_clicked)

        # Connect the action
        self.triggered.connect(self.start_tool)

    def start_tool(self):
        self.main.iface.mapCanvas().setMapTool(self.tool)

    def make_params(self, point):

        DEPARR = (
            "DEPARTURE" if self.widget.deparrComboBox.currentIndex() == 0 else "ARRIVAL"
        )

        input_layer = pointToLayer(point)
        time = self.widget.dateTimeEdit.dateTime().toUTC().toString(Qt.ISODate)

        transpt_type = self.widget.transptTypeComboBox.currentText()

        params = {
            "INPUT_" + DEPARR + "_SEARCHES": input_layer,
            "INPUT_" + DEPARR + "_TIME": "'" + time + "'",
            "INPUT_" + DEPARR + "_TRNSPT_TYPE": "'" + transpt_type + "'",
            "OUTPUT": "memory:",
        }

        if hasattr(self.widget, "travelTimeSpinBox"):
            travel_time = self.widget.travelTimeSpinBox.value() * 60
            params.update({"INPUT_" + DEPARR + "_TRAVEL_TIME": travel_time})

        return params

    def tool_clicked(self, point):
        params = self.make_params(point)

        class Feedback(QgsProcessingFeedback):
            def __init__(self):
                super().__init__()
                self.fatal_errors = []

            def reportError(self, error, fatalError=False):
                log(error)
                if fatalError:
                    self.fatal_errors.append(error)

        feedback = Feedback()
        try:
            # TODO : use QgsProcessingAlgRunnerTask to do this as a bg task
            processing.runAndLoadResults(self._algorithm, params, feedback=feedback)
        except QgsProcessingException as e:
            print(e)
            self.main.iface.messageBar().pushMessage(
                "Error",
                ", ".join(feedback.fatal_errors),
                level=Qgis.Critical,
                duration=0,
            )


class ExpressTimeMapAction(ExpressActionBase):
    _icon = resources.icon_time_map_express
    _name = tr("Quick time map")
    _widget_ui = "ExpressTimeMapWidget.ui"
    _algorithm = "ttp_v4:time_map"


class ExpressTimeFilterAction(ExpressActionBase):
    _icon = resources.icon_time_filter_express
    _name = tr("Quick time filter")
    _widget_ui = "ExpressTimeFilterWidget.ui"
    _algorithm = "ttp_v4:time_filter"

    def __init__(self, main):
        super().__init__(main)
        self.setEnabled(False)
        self.main.iface.currentLayerChanged.connect(self.current_layer_changed)

    def current_layer_changed(self, layer):
        self.setEnabled(
            layer is not None
            and layer.type() == QgsMapLayer.LayerType.VectorLayer
            and layer.geometryType() == QgsWkbTypes.PointGeometry
        )

    def make_params(self, point):
        params = super().make_params(point)
        params.update({"INPUT_LOCATIONS": self.main.iface.activeLayer()})
        return params


class ExpressRouteAction(ExpressActionBase):
    _icon = resources.icon_routes_express
    _name = tr("Quick route")
    _widget_ui = "ExpressRouteWidget.ui"
    _algorithm = "ttp_v4:routes"

    def __init__(self, main):
        super().__init__(main)
        self.marker = None
        self.point_a = None
        self.tool.deactivated.connect(self.cleanup)
        self.cleanup()

    def tool_clicked(self, point):
        if self.point_a is None:
            self.point_a = QgsPointXY(point)
            self.marker = QgsVertexMarker(self.main.iface.mapCanvas())
            self.marker.setCenter(self.point_a)
        else:
            super().tool_clicked(point)
            self.point_a = None
            self.main.iface.mapCanvas().scene().removeItem(self.marker)

    def cleanup(self):
        if self.marker:
            self.main.iface.mapCanvas().scene().removeItem(self.marker)
        self.marker = None
        self.point_a = None

    def make_params(self, point):
        locations_layer = pointToLayer(self.point_a)
        params = super().make_params(point)
        params.update({"INPUT_LOCATIONS": locations_layer, "OUTPUT_RESULT_TYPE": 1})
        log(params)
        return params


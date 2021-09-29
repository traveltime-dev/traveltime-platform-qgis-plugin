import os

import processing
from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsMapLayer,
    QgsPointXY,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProject,
    QgsReferencedPointXY,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapMouseEvent, QgsMapToolEmitPoint, QgsVertexMarker
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDateTime, QEvent, Qt, QVariant
from qgis.PyQt.QtWidgets import QAction, QMenu, QWidget, QWidgetAction

from . import resources
from .algorithms.base import THROTTLING_DISABLED, THROTTLING_STRATEGIES
from .utils import log, tr


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


def transform(src_crs, dst_crs, point):
    xform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
    return xform.transform(point)


class Feedback(QgsProcessingFeedback):
    """To provide feedback to the message bar from the express tools"""

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.fatal_errors = []

    def reportError(self, error, fatalError=False):
        log(error)
        if fatalError:
            self.fatal_errors.append(error)

    def pushToUser(self, exception):
        log(exception)
        self.iface.messageBar().pushMessage(
            "Error", ", ".join(self.fatal_errors), level=Qgis.Critical, duration=0
        )


class ExpressActionBase(QAction):
    _icon = None  # to be defined by subclasses
    _name = None  # to be defined by subclasses

    def __init__(self, main):
        super().__init__(self._icon, self._name)
        self.main = main

        # Connect the action
        self.triggered.connect(self.start_tool)

    def start_tool(self):
        raise NotImplementedError("Not implemented")


class ExpressActionToolBase(ExpressActionBase):
    _algorithm = None  # to be defined by subclasses
    _widget_ui = None  # to be defined by subclasses

    def __init__(self, main):
        super().__init__(main)
        self.setCheckable(True)

        # Build the widget
        self.widget = QWidget()
        uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui", self._widget_ui), self.widget
        )

        self.widgetAction = QWidgetAction(self)
        self.widgetAction.setDefaultWidget(self.widget)

        self.menu = QMenu()
        self.menu.addAction(self.widgetAction)
        self.setMenu(self.menu)

        # Init form values
        self.widget.dateTimeEdit.setDateTime(QDateTime.currentDateTime())

        # Build the tool
        self.tool = QgsMapToolEmitPoint(self.main.iface.mapCanvas())
        self.tool.activated.connect(lambda: self.setChecked(True))
        self.tool.deactivated.connect(lambda: self.setChecked(False))
        self.tool.canvasClicked.connect(self.tool_clicked)

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
            "INPUT_THROTTLING_STRATEGY": THROTTLING_STRATEGIES.index(
                THROTTLING_DISABLED
            ),
            "OUTPUT": "memory:",
        }

        if hasattr(self.widget, "travelTimeSpinBox"):
            travel_time = self.widget.travelTimeSpinBox.value() * 60
            walking_time = min(900, travel_time)
            params.update({"INPUT_" + DEPARR + "_TRAVEL_TIME": travel_time})
            params.update({"INPUT_" + DEPARR + "_TRNSPT_WALKING_TIME": walking_time})

        return params

    def tool_clicked(self, point):
        params = self.make_params(point)

        feedback = Feedback(self.main.iface)
        try:
            # TODO : use QgsProcessingAlgRunnerTask to do this as a bg task
            processing.runAndLoadResults(self._algorithm, params, feedback=feedback)
        except QgsProcessingException as e:
            feedback.pushToUser(e)


class ExpressTimeMapAction(ExpressActionToolBase):
    _icon = resources.icon_time_map_express
    _name = tr("Quick time map")
    _widget_ui = "ExpressTimeMapWidget.ui"
    _algorithm = "ttp_v4:time_map"


class ExpressTimeFilterAction(ExpressActionToolBase):
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


class ExpressRouteAction(ExpressActionToolBase):
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
        params.update({"INPUT_LOCATIONS": locations_layer, "OUTPUT_RESULT_TYPE": 2})
        log(params)
        return params


class ExpressGeoclickAction(ExpressActionBase):
    _icon = resources.icon_geoclick
    _name = tr("Geocoded click : simulate mouse clicks using a textual address")

    def __init__(self, main, lineEdit):
        super().__init__(main)
        self.marker = None
        self.setEnabled(False)

        # Create a QLineEdit next to the action
        self.lineEdit = lineEdit
        lineEdit.setMaximumWidth(150)
        lineEdit.setPlaceholderText(tr("Enter an address..."))

        self.lineEdit.textChanged.connect(self.text_changed)
        self.lineEdit.returnPressed.connect(self.start_tool)

    def start_tool(self):

        address = self.lineEdit.text()

        # create a temporary memory layer with 1 feature
        vl = QgsVectorLayer("Point?crs=EPSG:4326", "temporary_points", "memory")
        vl.startEditing()
        vl.dataProvider().addAttributes([QgsField("address", QVariant.String)])
        f = QgsFeature(vl.dataProvider().fields())
        f.setAttribute("address", address)
        vl.dataProvider().addFeature(f)
        vl.commitChanges()

        # run the geocoding algorithm
        center = QgsReferencedPointXY(
            self.main.iface.mapCanvas().center(), QgsProject.instance().crs()
        )
        params = {
            "INPUT_DATA": vl,
            "OUTPUT_RESULT_TYPE": 1,
            "INPUT_QUERY_FIELD": '"address"',
            "INPUT_FOCUS": center,
            "INPUT_THROTTLING_STRATEGY": THROTTLING_STRATEGIES.index(
                THROTTLING_DISABLED
            ),
            "OUTPUT": "memory:",
        }

        feedback = Feedback(self.main.iface)
        try:
            # TODO : use QgsProcessingAlgRunnerTask to do this as a bg task
            result = processing.run("ttp_v4:geocoding", params, feedback=feedback)
            layer = result["OUTPUT"]
        except QgsProcessingException as e:
            feedback.pushToUser(e)
            return

        # Get the point in the project's CRS
        point = transform(
            layer.crs(), QgsProject.instance().crs(), layer.extent().center()
        )

        # Center to point
        self.main.iface.mapCanvas().setCenter(point)

        # Draw a marker
        if self.marker is not None:
            self.main.iface.mapCanvas().scene().removeItem(self.marker)
        self.marker = QgsVertexMarker(self.main.iface.mapCanvas())
        self.marker.setCenter(point)

        # Emulate a mouse click
        mapTool = self.main.iface.mapCanvas().mapTool()

        event = QgsMapMouseEvent(
            self.main.iface.mapCanvas(),
            QEvent.MouseButtonPress,
            mapTool.toCanvasCoordinates(point),
            Qt.LeftButton,
        )
        event.setMapPoint(point)
        mapTool.canvasPressEvent(event)
        mapTool.canvasReleaseEvent(event)

    def text_changed(self, text):
        self.setEnabled(bool(text))
        if self.marker is not None:
            self.main.iface.mapCanvas().scene().removeItem(self.marker)
            self.marker = None

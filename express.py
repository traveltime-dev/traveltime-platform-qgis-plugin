import os

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
    QgsProcessingException,
    Qgis,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsProcessingFeedback,
    QgsWkbTypes,
    QgsMapLayer,
)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker
from qgis.PyQt import uic

import processing

from .utils import tr, log
from . import resources


class Feedback(QgsProcessingFeedback):
    def __init__(self):
        super().__init__()
        self.fatal_errors = []

    def reportError(self, error, fatalError=False):
        log(error)
        if fatalError:
            self.fatal_errors.append(error)


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


class ExpressTimeMapTool(QgsMapToolEmitPoint):
    def __init__(self, action, canvas):
        super().__init__(canvas)
        self.action = action
        self.canvas = canvas

        self.activated.connect(lambda: self.action.setChecked(True))
        self.deactivated.connect(lambda: self.action.setChecked(False))

    def canvasPressEvent(self, e):

        DEPARR = (
            "DEPARTURE"
            if self.action.widget.deparrComboBox.currentIndex() == 0
            else "ARRIVAL"
        )

        input_layer = pointToLayer(self.toMapCoordinates(self.canvas.mouseLastXY()))
        time = self.action.widget.dateTimeEdit.dateTime().toUTC().toString(Qt.ISODate)
        travel_time = self.action.widget.travelTimeSpinBox.value() * 60
        transpt_type = self.action.widget.transptTypeComboBox.currentText()

        params = {
            "INPUT_" + DEPARR + "_SEARCHES": input_layer,
            "INPUT_" + DEPARR + "_TIME": "'" + time + "'",
            "INPUT_" + DEPARR + "_TRAVEL_TIME": travel_time,
            "INPUT_" + DEPARR + "_TRNSPT_TYPE": "'" + transpt_type + "'",
            "OUTPUT": "memory:",
        }

        feedback = Feedback()
        try:
            # TODO : use QgsProcessingAlgRunnerTask to do this as a bg task
            processing.runAndLoadResults("ttp_v4:time_map", params, feedback=feedback)
        except QgsProcessingException as e:
            self.action.main.iface.messageBar().pushMessage(
                "Error", ", ".join(feedback.fatal_errors), level=Qgis.Critical
            )


class ExpressTimeMapWidget(QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui", "ExpressTimeMapWidget.ui"),
            self,
        )

        self.dateTimeEdit.setDateTime(QDateTime.currentDateTime())

    # TODO : there's an annoying bug where mouse clicks are at wrong position after
    # the mouse hoever the menu... This fixes it, but also hides the widget when
    # selecting an option from a QComboBox
    # def leaveEvent(self, evt):
    #     self.parent().close()
    #     return super().leaveEvent(evt)


class ExpressTimeMapAction(QAction):
    def __init__(self, main):
        super().__init__(resources.icon_time_map_express, tr("Quick time map"))
        self.setCheckable(True)

        self.main = main

        self.widget = ExpressTimeMapWidget()

        self.widgetAction = QWidgetAction(self)
        self.widgetAction.setDefaultWidget(self.widget)

        self.menu = QMenu()
        # self.menu.aboutToShow.connect(self.start_tool)
        self.menu.addAction(self.widgetAction)
        self.setMenu(self.menu)

        self.triggered.connect(self.start_tool)

    def start_tool(self):
        self.tool = ExpressTimeMapTool(self, self.main.iface.mapCanvas())
        self.main.iface.mapCanvas().setMapTool(self.tool)


class ExpressTimeFilterTool(QgsMapToolEmitPoint):
    def __init__(self, action, canvas):
        super().__init__(canvas)
        self.action = action
        self.canvas = canvas

        self.activated.connect(lambda: self.action.setChecked(True))
        self.deactivated.connect(lambda: self.action.setChecked(False))

    def canvasPressEvent(self, e):

        DEPARR = (
            "DEPARTURE"
            if self.action.widget.deparrComboBox.currentIndex() == 0
            else "ARRIVAL"
        )

        input_layer = pointToLayer(self.toMapCoordinates(self.canvas.mouseLastXY()))
        locations_layer = self.action.main.iface.activeLayer()
        time = self.action.widget.dateTimeEdit.dateTime().toUTC().toString(Qt.ISODate)
        travel_time = self.action.widget.travelTimeSpinBox.value() * 60
        transpt_type = self.action.widget.transptTypeComboBox.currentText()

        params = {
            "INPUT_" + DEPARR + "_SEARCHES": input_layer,
            "INPUT_LOCATIONS": locations_layer,
            "INPUT_" + DEPARR + "_TIME": "'" + time + "'",
            "INPUT_" + DEPARR + "_TRAVEL_TIME": travel_time,
            "INPUT_" + DEPARR + "_TRNSPT_TYPE": "'" + transpt_type + "'",
            "OUTPUT": "memory:",
        }

        feedback = Feedback()
        try:
            # TODO : use QgsProcessingAlgRunnerTask to do this as a bg task
            processing.runAndLoadResults(
                "ttp_v4:time_filter", params, feedback=feedback
            )
        except QgsProcessingException as e:
            self.action.main.iface.messageBar().pushMessage(
                "Error", ", ".join(feedback.fatal_errors), level=Qgis.Critical
            )


class ExpressTimeFilterWidget(QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui", "ExpressTimeFilterWidget.ui"),
            self,
        )

        self.dateTimeEdit.setDateTime(QDateTime.currentDateTime())

    # TODO : there's an annoying bug where mouse clicks are at wrong position after
    # the mouse hoever the menu... This fixes it, but also hides the widget when
    # selecting an option from a QComboBox
    # def leaveEvent(self, evt):
    #     self.parent().close()
    #     return super().leaveEvent(evt)


class ExpressTimeFilterAction(QAction):
    def __init__(self, main):
        super().__init__(resources.icon_time_filter_express, tr("Quick time filter"))
        self.setCheckable(True)
        self.setEnabled(False)

        self.main = main

        self.widget = ExpressTimeFilterWidget()

        self.widgetAction = QWidgetAction(self)
        self.widgetAction.setDefaultWidget(self.widget)

        self.menu = QMenu()
        # self.menu.aboutToShow.connect(self.start_tool)
        self.menu.addAction(self.widgetAction)
        self.setMenu(self.menu)

        self.main.iface.currentLayerChanged.connect(self.current_layer_changed)

        self.triggered.connect(self.start_tool)

    def current_layer_changed(self, layer):
        self.setEnabled(
            layer is not None
            and layer.type() == QgsMapLayer.LayerType.VectorLayer
            and layer.geometryType() == QgsWkbTypes.PointGeometry
        )

    def start_tool(self):
        self.tool = ExpressTimeFilterTool(self, self.main.iface.mapCanvas())
        self.main.iface.mapCanvas().setMapTool(self.tool)


class ExpressRouteTool(QgsMapToolEmitPoint):
    def __init__(self, action, canvas):
        super().__init__(canvas)
        self.action = action
        self.canvas = canvas

        self.activated.connect(lambda: self.action.setChecked(True))
        self.deactivated.connect(lambda: self.action.setChecked(False))
        self.deactivated.connect(self.cleanup)

        self.point_a = None
        self.marker = None

    def canvasPressEvent(self, e):

        if self.point_a is None:
            self.point_a = self.toMapCoordinates(self.canvas.mouseLastXY())
            self.marker = QgsVertexMarker(self.canvas)
            self.marker.setCenter(self.point_a)
            return

        DEPARR = (
            "DEPARTURE"
            if self.action.widget.deparrComboBox.currentIndex() == 0
            else "ARRIVAL"
        )

        input_layer = pointToLayer(self.point_a)
        locations_layer = pointToLayer(self.toMapCoordinates(self.canvas.mouseLastXY()))
        time = self.action.widget.dateTimeEdit.dateTime().toUTC().toString(Qt.ISODate)
        transpt_type = self.action.widget.transptTypeComboBox.currentText()

        params = {
            "INPUT_" + DEPARR + "_SEARCHES": input_layer,
            "INPUT_LOCATIONS": locations_layer,
            "INPUT_" + DEPARR + "_TIME": time,
            "INPUT_" + DEPARR + "_TRNSPT_TYPE": "'" + transpt_type + "'",
            "OUTPUT_RESULT_TYPE": 1,
            "OUTPUT": "memory:",
        }

        feedback = Feedback()
        try:
            # TODO : use QgsProcessingAlgRunnerTask to do this as a bg task
            processing.runAndLoadResults("ttp_v4:routes", params, feedback=feedback)
        except QgsProcessingException as e:
            self.action.main.iface.messageBar().pushMessage(
                "Error", ", ".join(feedback.fatal_errors), level=Qgis.Critical
            )

        self.cleanup()

    def cleanup(self):
        if self.marker:
            self.canvas.scene().removeItem(self.marker)
        self.point_a = None


class ExpressRouteWidget(QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui", "ExpressRouteWidget.ui"), self
        )

        self.dateTimeEdit.setDateTime(QDateTime.currentDateTime())

    # TODO : there's an annoying bug where mouse clicks are at wrong position after
    # the mouse hoever the menu... This fixes it, but also hides the widget when
    # selecting an option from a QComboBox
    # def leaveEvent(self, evt):
    #     self.parent().close()
    #     return super().leaveEvent(evt)


class ExpressRouteAction(QAction):
    def __init__(self, main):
        super().__init__(resources.icon_routes_express, tr("Quick route"))
        self.setCheckable(True)

        self.main = main

        self.widget = ExpressRouteWidget()

        self.widgetAction = QWidgetAction(self)
        self.widgetAction.setDefaultWidget(self.widget)

        self.menu = QMenu()
        # self.menu.aboutToShow.connect(self.start_tool)
        self.menu.addAction(self.widgetAction)
        self.setMenu(self.menu)

        self.triggered.connect(self.start_tool)

    def start_tool(self):
        self.tool = ExpressRouteTool(self, self.main.iface.mapCanvas())
        self.main.iface.mapCanvas().setMapTool(self.tool)

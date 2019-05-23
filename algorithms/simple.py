import os

from qgis.core import (
    QgsProcessing,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsFeature,
    QgsFeatureRequest,
    QgsProcessingUtils,
)

import processing

from .. import resources
from .. import parameters

from ..utils import tr

from .base import AlgorithmBase
from .advanced import TimeMapAlgorithm, TimeFilterAlgorithm, RoutesAlgorithm

TRANSPORTATION_TYPES = [
    "cycling",
    "driving",
    "driving+train",
    "public_transport",
    "walking",
    "coach",
    "bus",
    "train",
    "ferry",
    "driving+ferry",
    "cycling+ferry",
]


class _SimpleSearchAlgorithmBase(AlgorithmBase):
    _group = "Simplified"
    _groupId = "simple"
    _helpUrl = "http://docs.traveltimeplatform.com/reference/time-map/"

    SEARCH_TYPES = ["DEPARTURE", "ARRIVAL"]

    def initAlgorithm(self, config):

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_SEARCHES", tr("Searches"), [QgsProcessing.TypeVectorPoint]
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                "INPUT_SEARCH_TYPE", tr("Search type"), options=["departure", "arrival"]
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                "INPUT_TRNSPT_TYPE",
                tr("Transportation type"),
                options=TRANSPORTATION_TYPES,
            )
        )
        self.addParameter(
            parameters.ParameterIsoDateTime(
                "INPUT_TIME", tr("Departure/Arrival time (UTC)")
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "INPUT_TRAVEL_TIME",
                tr("Travel time (in minutes)"),
                type=0,
                defaultValue=15,
                minValue=0,
                maxValue=240,
            )
        )

        # OUTPUT
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT", tr("Output layer"), type=self.subalgorithm.output_type
            )
        )

    def processAlgorithmPrepareSubParameters(self, parameters, context, feedback):

        search_layer = self.params["INPUT_SEARCHES"].materialize(QgsFeatureRequest())

        mode = self.SEARCH_TYPES[self.params["INPUT_SEARCH_TYPE"]]

        trnspt_type = TRANSPORTATION_TYPES[self.params["INPUT_TRNSPT_TYPE"]]

        return {
            "INPUT_{}_SEARCHES".format(mode): search_layer,
            "INPUT_{}_TRNSPT_TYPE".format(mode): "'" + trnspt_type + "'",
            "INPUT_{}_TIME".format(mode): "'" + self.params["INPUT_TIME"] + "'",
            "INPUT_{}_TRAVEL_TIME".format(mode): str(
                self.params["INPUT_TRAVEL_TIME"] * 60
            ),
            "INPUT_{}_TRNSPT_WALKING_TIME".format(mode): str(
                self.params["INPUT_TRAVEL_TIME"] * 60
            ),
            "OUTPUT_RESULT_TYPE": self.params["OUTPUT_RESULT_TYPE"],
            "OUTPUT": "memory:results",
        }

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo("Starting TimeMapSimpleAlgorithm...")

        # Configure common expressions inputs
        self.processAlgorithmConfigureParams(parameters, context, feedback)

        # Prepare parameters for the sub algorithm
        sub_parameters = self.processAlgorithmPrepareSubParameters(
            parameters, context, feedback
        )

        feedback.pushDebugInfo("Calling subcommand with following parameters...")
        feedback.pushDebugInfo(str(sub_parameters))

        sub_id = "ttp_v4:" + self.subalgorithm._name
        results = processing.run(
            sub_id, sub_parameters, context=context, feedback=feedback
        )

        feedback.pushDebugInfo("Got results fom subcommand...")

        # For some reason, this doesn't work directly... We'll create a copy...
        # return results

        result_layer = results["OUTPUT"]

        # Configure output
        (sink, sink_id) = self.parameterAsSink(
            parameters,
            "OUTPUT",
            context,
            result_layer.fields(),
            result_layer.wkbType(),
            result_layer.sourceCrs(),
        )
        # Copy results to output
        feedback.pushDebugInfo("Copying results to layer...")
        for f in result_layer.getFeatures():
            sink.addFeature(QgsFeature(f))

        feedback.pushDebugInfo("{} done !".format(self.__class__.__name__))

        # to get hold of the layer in post processing
        self.sink_id = sink_id

        return {"OUTPUT": sink_id}


class TimeMapSimpleAlgorithm(_SimpleSearchAlgorithmBase):
    subalgorithm = TimeMapAlgorithm

    _name = "time_map_simple"
    _displayName = tr("Time Map - Simple")
    _group = "Simplified"
    _groupId = "simple"
    _icon = resources.icon_time_map_simple
    _helpUrl = "http://docs.traveltimeplatform.com/reference/time-map/"
    _shortHelpString = tr(
        "This algorithms provides a simpified access to the time-map endpoint.\n\nPlease see the help on {url} for more details on how to use it."
    ).format(url=_helpUrl)

    RESULT_TYPE = ["NORMAL", "UNION", "INTERSECTION"]

    def processAlgorithmPrepareSubParameters(self, parameters, context, feedback):
        params = super().processAlgorithmPrepareSubParameters(
            parameters, context, feedback
        )

        params.update({"OUTPUT_RESULT_TYPE": self.params["OUTPUT_RESULT_TYPE"]})

        return params

    def initAlgorithm(self, config):

        super().initAlgorithm(config)

        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_RESULT_TYPE", tr("Result aggregation"), options=self.RESULT_TYPE
            ),
            help_text=tr(
                "NORMAL will return a polygon for each departure/arrival search. UNION will return the union of all polygons for all departure/arrivals searches. INTERSECTION will return the intersection of all departure/arrival searches."
            ),
        )

    def postProcessAlgorithm(self, context, feedback):

        result_type = self.RESULT_TYPE[self.params["OUTPUT_RESULT_TYPE"]]

        if result_type == "NORMAL":
            style_file = "style_time.qml"
        elif result_type == "UNION":
            style_file = "style_time_union.qml"
        elif result_type == "INTERSECTION":
            style_file = "style_time_intersection.qml"

        style_path = os.path.join(os.path.dirname(__file__), "styles", style_file)
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(
            style_path
        )

        return super().postProcessAlgorithm(context, feedback)


class TimeFilterSimpleAlgorithm(_SimpleSearchAlgorithmBase):
    subalgorithm = TimeFilterAlgorithm

    _name = "time_filter_simple"
    _displayName = tr("Time Filter - Simple")
    _group = "Simplified"
    _groupId = "simple"
    _icon = resources.icon_time_filter_simple
    _helpUrl = "http://docs.traveltimeplatform.com/reference/time-filter/"
    _shortHelpString = tr(
        "This algorithms provides a simpified access to the time-filter endpoint.\n\nPlease see the help on {url} for more details on how to use it."
    ).format(url=_helpUrl)

    def processAlgorithmPrepareSubParameters(self, parameters, context, feedback):
        params = super().processAlgorithmPrepareSubParameters(
            parameters, context, feedback
        )

        locations_layer = self.params["INPUT_LOCATIONS"].materialize(
            QgsFeatureRequest()
        )

        params.update({"INPUT_LOCATIONS": locations_layer})

        return params

    def initAlgorithm(self, config):

        super().initAlgorithm(config)

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_LOCATIONS", tr("Locations"), [QgsProcessing.TypeVectorPoint]
            )
        )

    def postProcessAlgorithm(self, context, feedback):
        style_file = "style_filter.qml"
        style_path = os.path.join(os.path.dirname(__file__), "styles", style_file)
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(
            style_path
        )
        return super().postProcessAlgorithm(context, feedback)


class RoutesSimpleAlgorithm(_SimpleSearchAlgorithmBase):
    subalgorithm = RoutesAlgorithm

    _name = "routes_simple"
    _displayName = tr("Routes - Simple")
    _group = "Simplified"
    _groupId = "simple"
    _icon = resources.icon_routes_simple
    _helpUrl = "http://docs.traveltimeplatform.com/reference/routes/"
    _shortHelpString = tr(
        "This algorithms provides a simpified access to the routes endpoint.\n\nPlease see the help on {url} for more details on how to use it."
    ).format(url=_helpUrl)

    RESULT_TYPE = ["NORMAL", "DETAILED"]

    def processAlgorithmPrepareSubParameters(self, parameters, context, feedback):
        params = super().processAlgorithmPrepareSubParameters(
            parameters, context, feedback
        )

        locations_layer = self.params["INPUT_LOCATIONS"].materialize(
            QgsFeatureRequest()
        )

        params.update(
            {
                "INPUT_LOCATIONS": locations_layer,
                "OUTPUT_RESULT_TYPE": self.params["OUTPUT_RESULT_TYPE"],
            }
        )

        return params

    def initAlgorithm(self, config):

        super().initAlgorithm(config)

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_LOCATIONS", tr("Locations"), [QgsProcessing.TypeVectorPoint]
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_RESULT_TYPE", tr("Output style"), options=self.RESULT_TYPE
            ),
            help_text=tr(
                "Normal will return a simple linestring for each route. Detailed will return several segments for each type of transportation for each route."
            ),
        )

    def postProcessAlgorithm(self, context, feedback):
        if self.RESULT_TYPE[self.params["OUTPUT_RESULT_TYPE"]] == "NORMAL":
            style_file = "style_route_duration.qml"
        else:
            style_file = "style_route_mode.qml"
        style_path = os.path.join(os.path.dirname(__file__), "styles", style_file)
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(
            style_path
        )
        return super().postProcessAlgorithm(context, feedback)

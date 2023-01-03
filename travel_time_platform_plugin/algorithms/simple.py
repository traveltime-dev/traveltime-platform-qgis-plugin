import processing
from qgis.core import (
    QgsFeatureRequest,
    QgsProcessing,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExpression,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
)
from qgis.PyQt.QtCore import QDateTime, Qt, QTimeZone

from .. import parameters, resources, utils
from ..utils import tr
from .advanced import RoutesAlgorithm, TimeFilterAlgorithm, TimeMapAlgorithm
from .base import THROTTLING_PER_SETTINGS, THROTTLING_STRATEGIES, AlgorithmBase

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
SEARCH_TYPES = [
    "DEPARTURE",
    "ARRIVAL",
]


class _SimpleSearchAlgorithmBase(AlgorithmBase):
    _group = "Simplified"
    _groupId = "simple"
    _helpUrl = "http://docs.traveltimeplatform.com/reference/time-map/"

    def initAlgorithm(self, config):

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_SEARCHES", tr("Searches"), [QgsProcessing.TypeVectorPoint]
            )
        )
        self.addParameter(
            QgsProcessingParameterExpression(
                "INPUT_ID",
                tr("Searches ID"),
                optional=True,
                defaultValue="'searches_' || $id",
                parentLayerParameterName="INPUT_SEARCHES",
            ),
            advanced=True,
            help_text=tr(
                "Used to identify this specific search in the results array. MUST be unique among all searches."
            ),
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                "INPUT_SEARCH_TYPE",
                tr("Search type"),
                options=SEARCH_TYPES,
                defaultValue=SEARCH_TYPES.index("DEPARTURE"),
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                "INPUT_TRNSPT_TYPE",
                tr("Transportation type"),
                options=TRANSPORTATION_TYPES,
                # TODO: not the best default
                defaultValue=TRANSPORTATION_TYPES.index("cycling"),
            )
        )
        self.addParameter(
            parameters.ParameterIsoDateTime("INPUT_TIME", tr("Departure/Arrival time"))
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                "SETTINGS_TIMEZONE",
                tr("Timezone"),
                options=utils.timezones,
                defaultValue=utils.timezones.index(utils.default_timezone),
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                "SETTINGS_ROBUST_MODE",
                tr("Robust mode"),
                optional=True,
                defaultValue=False,
            ),
            advanced=True,
        )

        # OUTPUT
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT", tr("Output layer"), type=self.subalgorithm.output_type
            )
        )

    def processAlgorithmPrepareSubParameters(self, parameters, context, feedback):

        search_layer = self.params["INPUT_SEARCHES"].materialize(QgsFeatureRequest())
        search_id_expression = self.params["INPUT_ID"]

        mode = SEARCH_TYPES[self.params["INPUT_SEARCH_TYPE"]]

        trnspt_type = TRANSPORTATION_TYPES[self.params["INPUT_TRNSPT_TYPE"]]

        time = QDateTime.fromString(self.params["INPUT_TIME"], Qt.ISODate)
        timezone_code = utils.timezones[self.params["SETTINGS_TIMEZONE"]]
        time.setTimeZone(QTimeZone(timezone_code.encode("ascii")))

        return {
            "INPUT_{}_SEARCHES".format(mode): search_layer,
            "INPUT_{}_ID".format(mode): search_id_expression.expression(),
            "INPUT_{}_TRNSPT_TYPE".format(mode): "'" + trnspt_type + "'",
            "INPUT_{}_TIME".format(mode): "'" + time.toString(Qt.ISODate) + "'",
            "INPUT_THROTTLING_STRATEGY": THROTTLING_STRATEGIES.index(
                THROTTLING_PER_SETTINGS
            ),
            "INPUT_ROBUST_MODE": self.params["SETTINGS_ROBUST_MODE"],
            "OUTPUT": "memory:results",
        }

    def doProcessAlgorithm(self, parameters, context, feedback):

        # Configure common expressions inputs
        self.processAlgorithmConfigureParams(parameters, context, feedback)

        # Prepare parameters for the sub algorithm
        sub_parameters = self.processAlgorithmPrepareSubParameters(
            parameters, context, feedback
        )

        feedback.pushDebugInfo("Calling subcommand with following parameters...")
        feedback.pushDebugInfo(str(sub_parameters))

        sub_id = "ttp_v4:" + self.subalgorithm._name
        results = processing.runAndLoadResults(
            sub_id, sub_parameters, context=context, feedback=feedback
        )

        feedback.pushDebugInfo("Got results fom subcommand...")

        # Keep reference for further post processing
        self.sink_id = results["OUTPUT"]

        return {"OUTPUT": self.sink_id}


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
    LEVELS_OF_DETAILS = ["lowest", "low", "medium", "high", "highest"]

    def processAlgorithmPrepareSubParameters(self, parameters, context, feedback):
        params = super().processAlgorithmPrepareSubParameters(
            parameters, context, feedback
        )

        mode = SEARCH_TYPES[self.params["INPUT_SEARCH_TYPE"]]

        level_of_detail = self.LEVELS_OF_DETAILS[self.params["INPUT_LEVEL_OF_DETAIL"]]
        no_holes = self.params["INPUT_NO_HOLES"]
        single_shape = self.params["INPUT_SINGLE_SHAPE"]

        params.update(
            {
                "INPUT_{}_TRAVEL_TIME".format(mode): str(
                    self.params["INPUT_TRAVEL_TIME"] * 60
                ),
                "INPUT_{}_TRNSPT_WALKING_TIME".format(mode): str(
                    min(900, self.params["INPUT_TRAVEL_TIME"] * 60)
                ),
                "INPUT_{}_EXISTING_FIELDS_TO_KEEP".format(mode): self.params[
                    "INPUT_EXISTING_FIELDS_TO_KEEP"
                ],
                f"INPUT_{mode}_LEVEL_OF_DETAIL": f"'{level_of_detail}'",
                f"INPUT_{mode}_NO_HOLES": "true" if no_holes else "false",
                f"INPUT_{mode}_SINGLE_SHAPE": "true" if single_shape else "false",
                "OUTPUT_RESULT_TYPE": self.params["OUTPUT_RESULT_TYPE"],
            }
        )

        return params

    def initAlgorithm(self, config):

        super().initAlgorithm(config)

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

        self.addParameter(
            QgsProcessingParameterField(
                "INPUT_EXISTING_FIELDS_TO_KEEP",
                "Fields to keep",
                optional=True,
                allowMultiple=True,
                parentLayerParameterName="INPUT_SEARCHES",
            ),
            advanced=True,
            help_text=tr("Set which fields should be joined back in the output layer."),
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                "INPUT_LEVEL_OF_DETAIL",
                tr("Level of detail"),
                options=self.LEVELS_OF_DETAILS,
                defaultValue=self.LEVELS_OF_DETAILS.index("lowest"),
            ),
            advanced=True,
            help_text=tr(
                "Defines the level of detail of the resulting shape. Not all levels are available to all API keys."
            ),
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                "INPUT_SINGLE_SHAPE",
                tr("Single shape"),
                defaultValue=False,
            ),
            advanced=True,
            help_text=tr(
                "Enable to return only one shape from the search results. The returned shape will be approximately the biggest one among search results. Note that this will likely result in loss in accuracy."
            ),
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                "INPUT_NO_HOLES",
                tr("No holes"),
                defaultValue=False,
            ),
            advanced=True,
            help_text=tr(
                "Enable to remove holes from returned polygons. Note that this will likely result in loss in accuracy."
            ),
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_RESULT_TYPE",
                tr("Result aggregation"),
                options=self.RESULT_TYPE,
                defaultValue=self.RESULT_TYPE.index("NORMAL"),
            ),
            help_text=tr(
                "NORMAL will return a polygon for each departure/arrival search. UNION will return the union of all polygons for all departure/arrivals searches. INTERSECTION will return the intersection of all departure/arrival searches."
            ),
        )


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
        input_id_expression = self.params["INPUT_LOCATIONS_ID"]

        mode = SEARCH_TYPES[self.params["INPUT_SEARCH_TYPE"]]

        params.update(
            {
                "INPUT_{}_TRAVEL_TIME".format(mode): str(
                    self.params["INPUT_TRAVEL_TIME"] * 60
                ),
                "INPUT_{}_TRNSPT_WALKING_TIME".format(mode): str(
                    min(900, self.params["INPUT_TRAVEL_TIME"] * 60)
                ),
                "INPUT_LOCATIONS": locations_layer,
                "INPUT_LOCATIONS_ID": input_id_expression.expression(),
                "PROPERTIES_FARES": self.params["PROPERTIES_FARES"],
            }
        )

        return params

    def initAlgorithm(self, config):

        super().initAlgorithm(config)

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

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_LOCATIONS", tr("Locations"), [QgsProcessing.TypeVectorPoint]
            )
        )
        self.addParameter(
            QgsProcessingParameterExpression(
                "INPUT_LOCATIONS_ID",
                "Locations ID",
                optional=True,
                defaultValue="'locations_' || $id",
                parentLayerParameterName="INPUT_LOCATIONS",
            ),
            advanced=True,
            help_text=tr(
                "Used to identify this specific location in the results array. MUST be unique among all locations."
            ),
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                "PROPERTIES_FARES", tr("Load fares information"), optional=True
            ),
            help_text=tr(
                "Retrieve the fares. Currently, this is only supported in the UK."
            ),
        )


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

    RESULT_TYPE = ["NORMAL", "DURATION", "DETAILED"]

    def processAlgorithmPrepareSubParameters(self, parameters, context, feedback):
        params = super().processAlgorithmPrepareSubParameters(
            parameters, context, feedback
        )

        locations_layer = self.params["INPUT_LOCATIONS"].materialize(
            QgsFeatureRequest()
        )
        input_id_expression = self.params["INPUT_LOCATIONS_ID"]

        params.update(
            {
                "INPUT_LOCATIONS": locations_layer,
                "INPUT_LOCATIONS_ID": input_id_expression.expression(),
                "PROPERTIES_FARES": self.params["PROPERTIES_FARES"],
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
            QgsProcessingParameterExpression(
                "INPUT_LOCATIONS_ID",
                "Locations ID",
                optional=True,
                defaultValue="'locations_' || $id",
                parentLayerParameterName="INPUT_LOCATIONS",
            ),
            advanced=True,
            help_text=tr(
                "Used to identify this specific location in the results array. MUST be unique among all locations."
            ),
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                "PROPERTIES_FARES", tr("Load fares information"), optional=True
            ),
            help_text=tr(
                "Retrieve the fares. Currently, this is only supported in the UK."
            ),
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_RESULT_TYPE",
                tr("Output style"),
                options=self.RESULT_TYPE,
                defaultValue=self.RESULT_TYPE.index("NORMAL"),
            ),
            help_text=tr(
                "NORMAL and DURATION will return a simple linestring for each route. DETAILED will return several segments for each type of transportation for each route."
            ),
        )

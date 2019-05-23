import requests
import time
import json
import os
import math
import collections
from qgis.PyQt.QtCore import QVariant, QSettings
from qgis.PyQt.QtWidgets import QMessageBox

from qgis.core import (
    QgsMessageLog,
    QgsFeatureSink,
    QgsCoordinateTransform,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterExpression,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterMatrix,
    QgsProcessingParameterBoolean,
    QgsProcessingException,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterPoint,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsPoint,
    QgsLineString,
    QgsFields,
    QgsField,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsExpression,
    QgsFeatureRequest,
    QgsProcessingUtils,
)

import processing

from .libraries import requests_cache
from .libraries import iso3166

from . import resources
from . import auth
from . import utils
from . import parameters
from .utils import tr, log


EPSG4326 = QgsCoordinateReferenceSystem("EPSG:4326")
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
COUNTRIES = [(None, "-")] + list([(c.alpha2, c.name) for c in iso3166.countries])

cached_requests = requests_cache.core.CachedSession(
    # # Regular
    # cache_name="ttp_cache",
    # backend="memory",
    # Persisting (use for development, to avoid hitting API limit)
    cache_name=os.path.join(os.path.dirname(__file__), "cachefile"),
    backend="sqlite",
    expire_after=86400,
    allowable_methods=("GET", "POST"),
)


class AlgorithmBase(QgsProcessingAlgorithm):
    """Base class for all processing algorithms"""

    method = "POST"
    accept_header = "application/json"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parameters_help = {
            True: collections.OrderedDict(),
            False: collections.OrderedDict(),
        }

    def addParameter(self, parameter, advanced=False, help_text=None, *args, **kwargs):
        """Helper to add parameters with help texts"""
        if advanced:
            parameter.setFlags(
                parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        if help_text:
            self.parameters_help[advanced][parameter.description()] = help_text

        return super().addParameter(parameter, *args, **kwargs)

    def eval_expr(self, key):
        """Helper to evaluate an expression from the input.

        Do not forget to call self.expressions_context.setFeature(feature) before using this."""
        if key in self.params:
            return self.params[key].evaluate(self.expressions_context)
        else:
            return None

    def processAlgorithmConfigureParams(self, parameters, context, feedback):
        """Helper method that sets up all expressions parameter"""
        self.expressions_context = self.createExpressionContext(parameters, context)
        self.params = {}
        for p in self.parameterDefinitions():
            param = None
            if p.type() == "expression":
                param = QgsExpression(
                    self.parameterAsExpression(parameters, p.name(), context)
                )
                param.prepare(self.expressions_context)
            elif p.type() == "source":
                param = self.parameterAsSource(parameters, p.name(), context)
            elif p.type() == "enum":
                param = self.parameterAsEnum(parameters, p.name(), context)
            elif p.type() == "string":
                param = self.parameterAsString(parameters, p.name(), context)
            elif p.type() == "ttp_datetime":
                param = self.parameterAsString(parameters, p.name(), context)
            elif p.type() == "number":
                if p.dataType() == QgsProcessingParameterNumber.Type.Integer:
                    param = self.parameterAsInt(parameters, p.name(), context)
                else:
                    param = self.parameterAsDouble(parameters, p.name(), context)

            self.params[p.name()] = param

    def processAlgorithmMakeRequest(
        self, parameters, context, feedback, data=None, params={}
    ):
        """Helper method to check the API limits and make an authenticated request"""

        json_data = json.dumps(data)

        # Get API key
        APP_ID, API_KEY = auth.get_app_id_and_api_key()
        if not APP_ID or not API_KEY:
            feedback.reportError(
                tr(
                    "You need a Travel Time Platform API key to make requests. Please head to {} to obtain one, and enter it in the plugin's setting dialog."
                ).format("http://docs.traveltimeplatform.com/overview/getting-keys/"),
                fatalError=True,
            )
            raise QgsProcessingException("App ID or api key not set")

        headers = {
            "Content-type": "application/json",
            "Accept": self.accept_header,
            "X-Application-Id": APP_ID,
            "X-Api-Key": API_KEY,
        }

        feedback.pushDebugInfo("Making request to API endpoint...")
        print_query = bool(QSettings().value("travel_time_platform/log_calls", False))
        if print_query:
            log("Making request")
            log("url: {}".format(self.url))
            log("headers: {}".format(headers))
            log("params: {}".format(str(params)))
            log("data: {}".format(json_data))

        try:

            disable_https = QSettings().value(
                "travel_time_platform/disable_https", False, type=bool
            )
            if disable_https:
                feedback.pushInfo(
                    tr(
                        "Warning ! HTTPS certificate verification is disabled. This means all data sent to the API can potentially be intercepted by an attacker."
                    )
                )

            response = cached_requests.request(
                self.method,
                self.url,
                data=json_data,
                params=params,
                headers=headers,
                verify=not disable_https,
            )

            if response.from_cache:
                feedback.pushDebugInfo("Got response from cache...")
            else:
                feedback.pushDebugInfo("Got response from API endpoint...")
                QSettings().setValue(
                    "travel_time_platform/current_count",
                    int(QSettings().value("travel_time_platform/current_count", 0)) + 1,
                )

            if print_query:
                log("Got response")
                log("status: {}".format(response.status_code))
                log("reason: {}".format(response.reason))
                log("text: {}".format(response.text))

            response_data = json.loads(response.text)
            response.raise_for_status()

            return response_data

        except requests.exceptions.HTTPError as e:
            nice_info = "\n".join(
                "\t{}:\t{}".format(k, v)
                for k, v in response_data["additional_info"].items()
            )
            feedback.reportError(
                tr(
                    "Recieved error from the API.\nError code : {}\nDescription : {}\nSee : {}\nAddtionnal info :\n{}"
                ).format(
                    response_data["error_code"],
                    response_data["description"],
                    response_data["documentation_link"],
                    nice_info,
                ),
                fatalError=True,
            )
            feedback.reportError(tr("See log for more details."), fatalError=True)
            log(e)
            raise QgsProcessingException(
                "Got error {} from API".format(response.status_code)
            ) from None
        except requests.exceptions.SSLError as e:
            feedback.reportError(
                tr(
                    "Could not connect to the API because of an SSL certificate error. You can disable SSL verification in the plugin settings. See log for more details."
                ),
                fatalError=True,
            )
            log(e)
            raise QgsProcessingException(
                "Got an SSL error when connecting to the API"
            ) from None
        except requests.exceptions.RequestException as e:
            feedback.reportError(
                tr("Could not connect to the API. See log for more details."),
                fatalError=True,
            )
            log(e)
            raise QgsProcessingException("Could not connect to API") from None
        except ValueError as e:
            feedback.reportError(
                tr("Could not decode response. See log for more details."),
                fatalError=True,
            )
            log(e)
            raise QgsProcessingException("Could not decode response") from None

    def processAlgorithmEnforceLimit(
        self, queries_count, parameters, context, feedback
    ):
        s = QSettings()
        enabled = bool(s.value("travel_time_platform/warning_enabled", True))
        count = int(s.value("travel_time_platform/current_count", 0))
        limit = int(s.value("travel_time_platform/warning_limit", 10)) + 1

        feedback.pushDebugInfo("Checking API limit warnings...")

        if enabled and count + queries_count >= limit:
            feedback.reportError(
                tr(
                    "WARNING : API usage warning limit reached ({} calls remaining, {} calls planned) !"
                ).format(limit - count - 1, queries_count),
                fatalError=True,
            )
            feedback.reportError(
                tr(
                    "To continue, disable or increase the limit in the plugin settings, or reset the queries counter."
                ),
                fatalError=True,
            )
            raise QgsProcessingException("API usage limit warning")

        if enabled:
            feedback.pushInfo(
                tr(
                    "API usage warning limit not reached yet ({} calls remaining, {} calls planned)..."
                ).format(limit - count - 1, queries_count)
            )
        else:
            feedback.pushInfo(tr("API usage warning limit disabled..."))

    def createInstance(self):
        return self.__class__()

    # Cosmetic methods to allow less verbose definition of these propreties in child classes

    def name(self):
        return self._name

    def displayName(self):
        return self._displayName

    def group(self):
        return self._group

    def groupId(self):
        return self._groupId

    def icon(self):
        return self._icon

    def helpUrl(self):
        return self._helpUrl

    def shortHelpString(self):
        help_string = self._shortHelpString
        if self.parameters_help[False]:
            help_string += "<h2>Parameters description</h2>" + "".join(
                [
                    "\n<b>{}</b>: {}".format(key, val)
                    for key, val in self.parameters_help[False].items()
                ]
            )
        if self.parameters_help[True]:
            help_string += "<h2>Advanced parameters description</h2>" + "".join(
                [
                    "\n<b>{}</b>: {}".format(key, val)
                    for key, val in self.parameters_help[True].items()
                ]
            )
        return help_string


class SearchAlgorithmBase(AlgorithmBase):
    """Base class for the algorithms that share properties such as departure/arrival_searches"""

    search_properties = []

    def initAlgorithm(self, config):
        """Base setup of the algorithm.

        This will setup parameters corresponding to departure_searches and arrival_searches,
        since they are common to all main algorithms.

        Subclasses should call this and then define their own parameters.

        Note that there are slight differences on the API side on the departure_searches and
        arrival_searches parameters: for the time-map endpoint, the coords are included in these
        parameters, while for the time-filter and routes endpoints, the coords are all defined
        in a list of locations.

        Here we will implement everything as it is for the time-map endpoint, as it maps better
        to normal GIS workflow, where you usually have the list to filter and the inputs points
        as different datasets. The mapping to the different API data model will be done in the
        processing algorithm by the time-filter and routes subclasses.
        """

        for DEPARR in ["DEPARTURE", "ARRIVAL"]:
            self.addParameter(
                QgsProcessingParameterFeatureSource(
                    "INPUT_" + DEPARR + "_SEARCHES",
                    "{} / Searches".format(DEPARR.title()),
                    [QgsProcessing.TypeVectorPoint],
                    optional=True,
                ),
                help_text=tr(
                    "Searches based on departure time. Leave departure location at no earlier than given time. You can define a maximum of 10 searches"
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_ID",
                    "{} / ID".format(DEPARR.title()),
                    optional=True,
                    defaultValue="'" + DEPARR.lower() + "_searches_' || $id",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                help_text=tr(
                    "Used to identify this specific search in the results array. MUST be unique among all searches."
                ),
            )
            # Transportation
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_TRNSPT_TYPE",
                    "{} / Transportation / type".format(DEPARR.title()),
                    optional=True,
                    defaultValue="'public_transport'",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                help_text=tr(
                    "cycling, driving, driving+train (only in Great Britain), public_transport, walking, coach, bus, train, ferry, driving+ferry, cycling+ferry or cycling+public_transport (only in Netherlands)"
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_TRNSPT_PT_CHANGE_DELAY",
                    "{} / Transportation / change delay".format(DEPARR.title()),
                    optional=True,
                    defaultValue="0",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                advanced=True,
                help_text=tr(
                    "Time (in seconds) needed to board public transportation vehicle. Default is 0. Cannot be higher than travel_time. Used in public_transport, coach, bus, train, driving+train and cycling+public_transport transportation modes"
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_TRNSPT_WALKING_TIME",
                    "{} / Transportation / walking time".format(DEPARR.title()),
                    optional=True,
                    defaultValue="900",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                advanced=True,
                help_text=tr(
                    "Maximum time (in seconds) of walking from source to a station/stop and from station/stop to destination. Default value is 900. Cannot be higher than travel_time. Used in public_transport, coach, bus, train, driving+train and cycling+public_transport transportation modes"
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_TRNSPT_DRIVING_TIME_TO_STATION",
                    "{} / Transportation / driving time to station".format(
                        DEPARR.title()
                    ),
                    optional=True,
                    defaultValue="1800",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                advanced=True,
                help_text=tr(
                    "Maximum time (in seconds) of driving from source to train station. Default value is 1800. Cannot be higher than travel_time. Used in driving+train transportation mode"
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_TRNSPT_CYCLING_TIME_TO_STATION",
                    "{} / Transportation / cycling time to station".format(
                        DEPARR.title()
                    ),
                    optional=True,
                    defaultValue="900",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                advanced=True,
                help_text=tr(
                    "Maximum time (in seconds) of cycling (including any ferry transfers) from source to a station or stop. Default value is 900. Cannot be higher than travel_time. Used in cycling+public_transport transportation mode"
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_TRNSPT_PARKING_TIME",
                    "{} / Transportation / parking time".format(DEPARR.title()),
                    optional=True,
                    defaultValue="300",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                advanced=True,
                help_text=tr(
                    "Time (in seconds) required to park a car or a bike. Default is 300. Cannot be higher than travel_time. Used in driving+train and cycling+public_transport transportation modes."
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_TRNSPT_BOARDING_TIME",
                    "{} / Transportation / boarding time".format(DEPARR.title()),
                    optional=True,
                    defaultValue="0",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                advanced=True,
                help_text=tr(
                    "Time (in seconds) required to board a ferry. Default is 0. Cannot be higher than travel_time. Used in public_transport, ferry, driving+ferry, cycling+ferry and cycling+public_transport transportation modes. For public_transport mode, pt_change_delay is used instead"
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_RANGE_WIDTH",
                    "{} / Search range width ".format(DEPARR.title()),
                    optional=True,
                    defaultValue="null",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                advanced=True,
                help_text=tr(
                    "Search range width in seconds. width along with departure_time specify departure interval. For example, if you set departure_time to 9am and width to 1 hour, we will return a combined shape of all possible journeys that have departure time between 9am and 10am. Range width is limited to 12 hours"
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_TIME",
                    "{} / Time".format(DEPARR.title()),
                    optional=True,
                    defaultValue="'{}'".format(utils.now_iso()),
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                help_text=tr(
                    "Leave departure location at no earlier than given time. Example - 2017-10-18T08:00:00Z"
                ),
            )
            self.addParameter(
                QgsProcessingParameterExpression(
                    "INPUT_" + DEPARR + "_TRAVEL_TIME",
                    "{} / Travel time".format(DEPARR.title()),
                    optional=True,
                    defaultValue="900",
                    parentLayerParameterName="INPUT_" + DEPARR + "_SEARCHES",
                ),
                help_text=tr(
                    "Travel time in seconds. Maximum value is 14400 (4 hours)"
                ),
            )

        # Define output parameters
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT", tr("Output"), type=self.output_type
            )
        )

    def processAlgorithmGetSlices(self, parameters, context, feedback):
        """Gets the slices to subdivide queries in smaller chunks"""
        slices = list(self._processAlgorithmYieldSlices(parameters, context, feedback))

        if len(slices) > 1:
            feedback.pushInfo(
                tr(
                    "Due to the large amount of features, the request will be chunked in {} API calls. This may have unexpected consequences on some parameters. Keep an eye on your API usage !"
                ).format(len(slices))
            )

        # Make sure we don't hit the API limit
        self.processAlgorithmEnforceLimit(len(slices), parameters, context, feedback)

        return slices

    def _processAlgorithmYieldSlices(self, parameters, context, feedback):
        """Yields slices to subdivide queries in smaller chunks"""

        departure_count = (
            self.params["INPUT_DEPARTURE_SEARCHES"].featureCount()
            if self.params["INPUT_DEPARTURE_SEARCHES"]
            else 0
        )
        arrival_count = (
            self.params["INPUT_ARRIVAL_SEARCHES"].featureCount()
            if self.params["INPUT_ARRIVAL_SEARCHES"]
            else 0
        )

        slicing_size = 10
        slicing_count = math.ceil(max(departure_count, arrival_count) / slicing_size)

        for i in range(slicing_count):
            yield {
                "search_slice_start": i * slicing_size,
                "search_slice_end": (i + 1) * slicing_size,
            }

    def processAlgorithmPrepareSearchData(
        self, slicing_start, slicing_end, parameters, context, feedback
    ):
        """This method prepares the data array with all parameters corresponding to the common search attributes

        The slicing_start/end params allow to prepare just a slice, to conform to API limitation (for now 10 searches/query)
        """
        data = {}
        for DEPARR in ["DEPARTURE", "ARRIVAL"]:
            source = self.params["INPUT_" + DEPARR + "_SEARCHES"]
            deparr = DEPARR.lower()
            if source:
                feedback.pushDebugInfo("Loading {} searches features...".format(deparr))
                data[deparr + "_searches"] = []
                xform = QgsCoordinateTransform(
                    source.sourceCrs(), EPSG4326, context.transformContext()
                )
                for i, feature in enumerate(source.getFeatures()):
                    # Stop the algorithm if cancel button has been clicked
                    # if feedback.isCanceled():
                    #     break

                    if i < slicing_start or i >= slicing_end:
                        continue

                    # Set feature for expression context
                    self.expressions_context.setFeature(feature)

                    # Reproject to WGS84
                    geometry = feature.geometry()
                    geometry.transform(xform)

                    search_data = {
                        "id": self.eval_expr("INPUT_" + DEPARR + "_ID"),
                        "coords": {
                            "lat": geometry.asPoint().y(),
                            "lng": geometry.asPoint().x(),
                        },
                        "transportation": {
                            "type": self.eval_expr("INPUT_" + DEPARR + "_TRNSPT_TYPE"),
                            "pt_change_delay": self.eval_expr(
                                "INPUT_" + DEPARR + "_TRNSPT_PT_CHANGE_DELAY"
                            ),
                            "walking_time": self.eval_expr(
                                "INPUT_" + DEPARR + "_TRNSPT_WALKING_TIME"
                            ),
                            "driving_time_to_station": self.eval_expr(
                                "INPUT_" + DEPARR + "_TRNSPT_DRIVING_TIME_TO_STATION"
                            ),
                            "cycling_time_to_station": self.eval_expr(
                                "INPUT_" + DEPARR + "_TRNSPT_CYCLING_TIME_TO_STATION"
                            ),
                            "parking_time": self.eval_expr(
                                "INPUT_" + DEPARR + "_TRNSPT_PARKING_TIME"
                            ),
                            "boarding_time": self.eval_expr(
                                "INPUT_" + DEPARR + "_TRNSPT_BOARDING_TIME"
                            ),
                        },
                        deparr + "_time": self.eval_expr("INPUT_" + DEPARR + "_TIME"),
                        "travel_time": self.eval_expr(
                            "INPUT_" + DEPARR + "_TRAVEL_TIME"
                        ),
                        # TODO : allow to edit properties
                        "properties": self.search_properties,
                    }
                    range_width = self.eval_expr("INPUT_" + DEPARR + "_RANGE_WIDTH")
                    if range_width:
                        search_data.update(
                            {"range": {"enabled": True, "width": range_width}}
                        )

                    data[deparr + "_searches"].append(search_data)

                    # # Update the progress bar
                    # feedback.setProgress(int(current * total))
        return data


class TimeMapAlgorithm(SearchAlgorithmBase):
    url = "https://api.traveltimeapp.com/v4/time-map"
    accept_header = "application/vnd.wkt+json"
    output_type = QgsProcessing.TypeVectorPolygon

    _name = "time_map"
    _displayName = "Time Map"
    _group = "Advanced"
    _groupId = "advanced"
    _icon = resources.icon_time_map_advanced
    _helpUrl = "http://docs.traveltimeplatform.com/reference/time-map/"
    _shortHelpString = tr(
        "This algorithms allows to use the time-map endpoint from the Travel Time Platform API.\n\nIt matches the endpoint data structure as closely as possible. Please see the help on {url} for more details on how to use it.\n\nConsider using the simplified algorithms as they may be easier to work with."
    ).format(url=_helpUrl)

    RESULT_TYPE = ["NORMAL", "UNION", "INTERSECTION"]

    def initAlgorithm(self, config):

        # Define all common DEPARTURE and ARRIVAL parameters
        super().initAlgorithm(config)

        # Define additional input parameters
        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_RESULT_TYPE", tr("Result aggregation"), options=self.RESULT_TYPE
            ),
            help_text=tr(
                "NORMAL will return a polygon for each departure/arrival search. UNION will return the union of all polygons for all departure/arrivals searches. INTERSECTION will return the intersection of all departure/arrival searches."
            ),
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo("Starting {}...".format(self.__class__.__name__))

        # Configure common expressions inputs
        self.processAlgorithmConfigureParams(parameters, context, feedback)

        # Slice queries if needed
        slices = self.processAlgorithmGetSlices(parameters, context, feedback)

        # Make the query (in slices)
        results = []
        for slice_ in slices:

            slc_start = slice_["search_slice_start"]
            slc_end = slice_["search_slice_end"]

            # Prepare the data
            data = self.processAlgorithmPrepareSearchData(
                slc_start, slc_end, parameters, context, feedback
            )

            # Remix the data as needed
            data = self.processAlgorithmRemixData(data, parameters, context, feedback)

            # Make the query
            response_data = self.processAlgorithmMakeRequest(
                parameters, context, feedback, data=data
            )

            results += response_data["results"]

        feedback.pushDebugInfo("Loading response to layer...")

        # Configure output
        return self.processAlgorithmOutput(results, parameters, context, feedback)

    def processAlgorithmRemixData(self, data, parameters, context, feedback):
        """To be overriden by subclasses : allow to edit the data object before sending to the API"""

        result_type = self.RESULT_TYPE[self.params["OUTPUT_RESULT_TYPE"]]

        if result_type != "NORMAL":
            search_ids = []
            for deparr in ["departure", "arrival"]:
                if deparr + "_searches" in data:
                    for d in data[deparr + "_searches"]:
                        search_ids.append(d["id"])
            if result_type == "UNION":
                data["unions"] = [{"id": "union_all", "search_ids": search_ids}]
            elif result_type == "INTERSECTION":
                data["intersections"] = [
                    {"id": "intersection_all", "search_ids": search_ids}
                ]

        return data

    def processAlgorithmOutput(self, results, parameters, context, feedback):
        output_fields = QgsFields()
        output_fields.append(QgsField("id", QVariant.String, "text", 255))
        output_fields.append(QgsField("properties", QVariant.String, "text", 255))

        (sink, sink_id) = self.parameterAsSink(
            parameters,
            "OUTPUT",
            context,
            output_fields,
            QgsWkbTypes.MultiPolygon,
            EPSG4326,
        )

        result_type = self.RESULT_TYPE[self.params["OUTPUT_RESULT_TYPE"]]

        for result in results:
            feature = QgsFeature(output_fields)
            feature.setAttribute(0, result["search_id"])
            feature.setAttribute(1, json.dumps(result["properties"]))
            feature.setGeometry(QgsGeometry.fromWkt(result["shape"]))

            # Add a feature in the sink
            if (
                result_type == "NORMAL"
                or (
                    result_type == "INTERSECTION"
                    and result["search_id"] == "intersection_all"
                )
                or (result_type == "UNION" and result["search_id"] == "union_all")
            ):
                sink.addFeature(feature, QgsFeatureSink.FastInsert)

        feedback.pushDebugInfo("TimeMapAlgorithm done !")

        # to get hold of the layer in post processing
        self.sink_id = sink_id

        return {"OUTPUT": sink_id}

    def postProcessAlgorithm(self, context, feedback):

        result_type = self.RESULT_TYPE[self.params["OUTPUT_RESULT_TYPE"]]

        if result_type == "NORMAL":
            style_file = "style.qml"
        elif result_type == "UNION":
            style_file = "style_union.qml"
        elif result_type == "INTERSECTION":
            style_file = "style_intersection.qml"

        style_path = os.path.join(os.path.dirname(__file__), "resources", style_file)
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(
            style_path
        )

        return super().postProcessAlgorithm(context, feedback)


class TimeFilterAlgorithm(SearchAlgorithmBase):
    url = "https://api.traveltimeapp.com/v4/time-filter"
    accept_header = "application/json"
    # search_properties = ["travel_time", "distance", "distance_breakdown", "fares", "route"]
    search_properties = ["travel_time", "distance", "distance_breakdown", "route"]
    output_type = QgsProcessing.TypeVectorPoint

    _name = "time_filter"
    _displayName = "Time Filter"
    _group = "Advanced"
    _groupId = "advanced"
    _icon = resources.icon_time_filter_advanced
    _helpUrl = "http://docs.traveltimeplatform.com/reference/time-filter/"
    _shortHelpString = tr(
        "This algorithms allows to use the time-filter endpoint from the Travel Time Platform API.\n\nIt matches the endpoint data structure as closely as possible. The key difference with the API is that the filter is automatically done on ALL locations, while the API technically allows to specify which locations to filter for each search.\n\nPlease see the help on {url} for more details on how to use it.\n\nConsider using the simplified algorithms as they may be easier to work with."
    ).format(url=_helpUrl)

    def initAlgorithm(self, config):

        # Define all common DEPARTURE and ARRIVAL parameters
        super().initAlgorithm(config)

        # Define additional input parameters
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_LOCATIONS",
                tr("Locations"),
                [QgsProcessing.TypeVectorPoint],
                optional=False,
            ),
            help_text=tr(
                "The list of locations to filter. In contrast to the API, this algorithm filters ALL locations, while the API allows to specify which arrival_location_ids/departure_location_ids to filter."
            ),
        )
        self.addParameter(
            QgsProcessingParameterExpression(
                "INPUT_LOCATIONS_ID",
                "Locations ID",
                optional=True,
                defaultValue="'locations_' || $id",
                parentLayerParameterName="INPUT_LOCATIONS",
            ),
            help_text=tr(
                "You will have to reference this id in your searches. It will also be used in the response body. MUST be unique among all locations."
            ),
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo("Starting {}...".format(self.__class__.__name__))

        # Configure common expressions inputs
        self.processAlgorithmConfigureParams(parameters, context, feedback)

        # Slice queries if needed
        slices = self.processAlgorithmGetSlices(parameters, context, feedback)

        # Make the query (in slices)
        results = []
        for slice_ in slices:

            slc_start = slice_["search_slice_start"]
            slc_end = slice_["search_slice_end"]

            # Prepare the data
            data = self.processAlgorithmPrepareSearchData(
                slc_start, slc_end, parameters, context, feedback
            )

            # Remix the data as needed
            data = self.processAlgorithmRemixData(
                data, slice_, parameters, context, feedback
            )

            # Make the query
            response_data = self.processAlgorithmMakeRequest(
                parameters, context, feedback, data=data
            )

            results += response_data["results"]

        feedback.pushDebugInfo("Loading response to layer...")

        # Configure output
        return self.processAlgorithmOutput(results, parameters, context, feedback)

    def processAlgorithmRemixData(self, data, slice_, parameters, context, feedback):
        locations = self.params["INPUT_LOCATIONS"]

        # Prepare location data (this is the same for all the slices)
        data["locations"] = []
        xform = QgsCoordinateTransform(
            locations.sourceCrs(), EPSG4326, context.transformContext()
        )

        slc_start = slice_["loc_slice_start"]
        slc_end = slice_["loc_slice_end"]

        for i, feature in enumerate(locations.getFeatures()):

            if i < slc_start or i >= slc_end:
                continue

            # Set feature for expression context
            self.expressions_context.setFeature(feature)
            geometry = feature.geometry()
            geometry.transform(xform)
            data["locations"].append(
                {
                    "id": self.eval_expr("INPUT_LOCATIONS_ID"),
                    "coords": {
                        "lat": geometry.asPoint().y(),
                        "lng": geometry.asPoint().x(),
                    },
                }
            )

        # Currently, the API requires all geoms to be passed in the locations parameter
        # and refers to them using departure_location_id and arrival_location_ids in the
        # departure_searches definition.
        # Here we remix the data array to conform to this data model.
        all_locations_ids = [l["id"] for l in data["locations"]]
        if "departure_searches" in data:
            for departure_search in data["departure_searches"]:
                data["locations"].append(
                    {"id": departure_search["id"], "coords": departure_search["coords"]}
                )
                del departure_search["coords"]
                departure_search["departure_location_id"] = departure_search["id"]
                departure_search["arrival_location_ids"] = all_locations_ids
        if "arrival_searches" in data:
            for arrival_search in data["arrival_searches"]:
                data["locations"].append(
                    {"id": arrival_search["id"], "coords": arrival_search["coords"]}
                )
                del arrival_search["coords"]
                arrival_search["arrival_location_id"] = arrival_search["id"]
                arrival_search["departure_location_ids"] = all_locations_ids

        return data

    def processAlgorithmOutput(self, results, parameters, context, feedback):
        locations = self.params["INPUT_LOCATIONS"]

        output_fields = QgsFields(locations.fields())
        output_fields.append(QgsField("search_id", QVariant.String, "text", 255))
        output_fields.append(QgsField("reachable", QVariant.Int, "int", 255))
        output_fields.append(QgsField("properties", QVariant.String, "text", 255))

        output_crs = locations.sourceCrs()
        output_type = locations.wkbType()

        QgsWkbTypes.MultiPolygon

        (sink, sink_id) = self.parameterAsSink(
            parameters, "OUTPUT", context, output_fields, output_type, output_crs
        )

        def clone_feature(id_):
            """Returns a feature cloned from the locations layer"""
            id_expr = self.params["INPUT_LOCATIONS_ID"]
            expression_ctx = self.createExpressionContext(parameters, context)
            expression = QgsExpression("{} = '{}'".format(id_expr, id_))
            return utils.clone_feature(
                QgsFeatureRequest(expression, expression_ctx), locations, output_fields
            )

        for result in results:
            for location in result["locations"]:
                feature = clone_feature(location["id"])
                feature.setAttribute(len(output_fields) - 3, result["search_id"])
                feature.setAttribute(len(output_fields) - 2, 1)
                feature.setAttribute(
                    len(output_fields) - 1, json.dumps(location["properties"])
                )
                sink.addFeature(feature, QgsFeatureSink.FastInsert)
            for id_ in result["unreachable"]:
                feature = clone_feature(id_)
                feature.setAttribute(len(output_fields) - 3, result["search_id"])
                feature.setAttribute(len(output_fields) - 2, 0)
                feature.setAttribute(len(output_fields) - 1, None)
                sink.addFeature(feature, QgsFeatureSink.FastInsert)

        feedback.pushDebugInfo("TimeFilterAlgorithm done !")

        # to get hold of the layer in post processing
        self.sink_id = sink_id

        return {"OUTPUT_RESULTS": sink_id}

    def postProcessAlgorithm(self, context, feedback):
        style_path = os.path.join(
            os.path.dirname(__file__), "resources", "style_filter.qml"
        )
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(
            style_path
        )
        return super().postProcessAlgorithm(context, feedback)

    def _processAlgorithmYieldSlices(self, parameters, context, feedback):
        """Yields slices to subdivide queries in smaller chunks"""

        locations_count = self.params["INPUT_LOCATIONS"].featureCount()

        slicing_size = 2000
        slicing_count = math.ceil(locations_count / slicing_size)

        for i in range(slicing_count):
            for slice_ in super()._processAlgorithmYieldSlices(
                parameters, context, feedback
            ):
                slice_.update(
                    {
                        "loc_slice_start": i * slicing_size,
                        "loc_slice_end": (i + 1) * slicing_size,
                    }
                )
                yield slice_


class RoutesAlgorithm(SearchAlgorithmBase):
    url = "https://api.traveltimeapp.com/v4/routes"
    accept_header = "application/json"
    # search_properties = ["travel_time", "distance", "route", "fares"]
    search_properties = ["travel_time", "distance", "route"]
    output_type = QgsProcessing.TypeVectorLine

    _name = "routes"
    _displayName = "Routes"
    _group = "Advanced"
    _groupId = "advanced"
    _icon = resources.icon_routes_advanced
    _helpUrl = "http://docs.traveltimeplatform.com/reference/routes/"
    _shortHelpString = tr(
        "This algorithms allows to use the routes endpoint from the Travel Time Platform API.\n\nIt matches the endpoint data structure as closely as possible. The key difference with the API is that the routes are automatically computd on ALL locations, while the API technically allows to specify which locations to filter for each search.\n\nPlease see the help on {url} for more details on how to use it.\n\nConsider using the simplified algorithms as they may be easier to work with."
    ).format(url=_helpUrl)

    RESULT_TYPE = ["NORMAL", "DETAILED"]

    def initAlgorithm(self, config):

        # Define all common DEPARTURE and ARRIVAL parameters
        super().initAlgorithm(config)

        # Remove unused parameters
        self.removeParameter("INPUT_DEPARTURE_TRAVEL_TIME")
        self.removeParameter("INPUT_ARRIVAL_TRAVEL_TIME")

        # Define additional input parameters
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_LOCATIONS",
                tr("Locations"),
                [QgsProcessing.TypeVectorPoint],
                optional=False,
            ),
            help_text=tr(
                "Define your locations to use later in departure_searches or arrival_searches"
            ),
        )
        self.addParameter(
            QgsProcessingParameterExpression(
                "INPUT_LOCATIONS_ID",
                "Locations ID",
                optional=True,
                defaultValue="'locations_' || $id",
                parentLayerParameterName="INPUT_LOCATIONS",
            ),
            help_text=tr(
                "You will have to reference this id in your searches. It will also be used in the response body. MUST be unique among all locations."
            ),
        )

        # Define output parameters
        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_RESULT_TYPE", tr("Output style"), options=self.RESULT_TYPE
            ),
            help_text=tr(
                "Normal will return a simple linestring for each route. Detailed will return several segments for each type of transportation for each route."
            ),
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo("Starting {}...".format(self.__class__.__name__))

        # Configure common expressions inputs
        self.processAlgorithmConfigureParams(parameters, context, feedback)

        # Slice queries if needed
        slices = self.processAlgorithmGetSlices(parameters, context, feedback)

        # Make the query (in slices)
        results = []
        for slice_ in slices:

            slc_start = slice_["search_slice_start"]
            slc_end = slice_["search_slice_end"]

            # Prepare the data
            data = self.processAlgorithmPrepareSearchData(
                slc_start, slc_end, parameters, context, feedback
            )

            # Remix the data as needed
            data = self.processAlgorithmRemixData(
                data, slice_, parameters, context, feedback
            )

            # Make the query
            response_data = self.processAlgorithmMakeRequest(
                parameters, context, feedback, data=data
            )

            results += response_data["results"]

        feedback.pushDebugInfo("Loading response to layer...")

        # Configure output
        return self.processAlgorithmOutput(results, parameters, context, feedback)

    def processAlgorithmRemixData(self, data, slice_, parameters, context, feedback):
        locations = self.params["INPUT_LOCATIONS"]

        # Prepare location data
        data["locations"] = []
        xform = QgsCoordinateTransform(
            locations.sourceCrs(), EPSG4326, context.transformContext()
        )

        slc_start = slice_["loc_slice_start"]
        slc_end = slice_["loc_slice_end"]

        for i, feature in enumerate(locations.getFeatures()):

            if i < slc_start or i >= slc_end:
                continue

            # Set feature for expression context
            self.expressions_context.setFeature(feature)
            geometry = feature.geometry()
            geometry.transform(xform)
            data["locations"].append(
                {
                    "id": self.eval_expr("INPUT_LOCATIONS_ID"),
                    "coords": {
                        "lat": geometry.asPoint().y(),
                        "lng": geometry.asPoint().x(),
                    },
                }
            )

        # Currently, the API requires all geoms to be passed in the locations parameter
        # and refers to them using departure_location_id and arrival_location_ids in the
        # departure_searches definition.
        # Here we remix the data array to conform to this data model.
        all_locations_ids = [l["id"] for l in data["locations"]]
        if "departure_searches" in data:
            for departure_search in data["departure_searches"]:
                data["locations"].append(
                    {"id": departure_search["id"], "coords": departure_search["coords"]}
                )
                del departure_search["coords"]
                del departure_search["travel_time"]
                departure_search["departure_location_id"] = departure_search["id"]
                departure_search["arrival_location_ids"] = all_locations_ids
        if "arrival_searches" in data:
            for arrival_search in data["arrival_searches"]:
                data["locations"].append(
                    {"id": arrival_search["id"], "coords": arrival_search["coords"]}
                )
                del arrival_search["coords"]
                del arrival_search["travel_time"]
                arrival_search["arrival_location_id"] = arrival_search["id"]
                arrival_search["departure_location_ids"] = all_locations_ids

        return data

    def processAlgorithmOutput(self, results, parameters, context, feedback):
        output_fields = QgsFields()
        result_type = self.RESULT_TYPE[self.params["OUTPUT_RESULT_TYPE"]]
        if result_type == "NORMAL":
            output_fields.append(QgsField("search_id", QVariant.String, "text", 255))
            output_fields.append(QgsField("location_id", QVariant.String, "text", 255))
            output_fields.append(QgsField("travel_time", QVariant.Double, "text", 255))
            output_fields.append(QgsField("distance", QVariant.Double, "text", 255))
            output_fields.append(
                QgsField("departure_time", QVariant.String, "text", 255)
            )
            output_fields.append(QgsField("arrival_time", QVariant.String, "text", 255))
        else:
            output_fields.append(QgsField("type", QVariant.String, "text", 255))
            output_fields.append(QgsField("mode", QVariant.String, "text", 255))
            output_fields.append(QgsField("directions", QVariant.String, "text", 255))

        output_crs = EPSG4326
        output_type = QgsWkbTypes.LineString

        (sink, sink_id) = self.parameterAsSink(
            parameters, "OUTPUT", context, output_fields, output_type, output_crs
        )

        for result in results:
            for location in result["locations"]:

                if result_type == "NORMAL":

                    # Create the geom
                    geom = QgsLineString()
                    for part in location["properties"][0]["route"]["parts"]:
                        for coord in part["coords"]:
                            point = QgsPoint(coord["lng"], coord["lat"])
                            if geom.endPoint() != point:
                                geom.addVertex(point)

                    # Create the feature
                    feature = QgsFeature(output_fields)
                    feature.setGeometry(geom)
                    feature.setAttribute(0, result["search_id"])
                    feature.setAttribute(1, location["id"])
                    feature.setAttribute(2, location["properties"][0]["travel_time"])
                    feature.setAttribute(3, location["properties"][0]["distance"])
                    feature.setAttribute(
                        4, location["properties"][0]["route"]["departure_time"]
                    )
                    feature.setAttribute(
                        5, location["properties"][0]["route"]["arrival_time"]
                    )
                    sink.addFeature(feature, QgsFeatureSink.FastInsert)
                else:
                    for part in location["properties"][0]["route"]["parts"]:

                        # Create the geom
                        geom = QgsLineString()
                        for coord in part["coords"]:
                            point = QgsPoint(coord["lng"], coord["lat"])
                            geom.addVertex(point)

                        # Create the feature
                        feature_d = QgsFeature(output_fields)
                        feature_d.setGeometry(geom)
                        feature_d.setAttribute(0, part["type"])
                        feature_d.setAttribute(1, part["mode"])
                        feature_d.setAttribute(2, part["directions"])
                        sink.addFeature(feature_d, QgsFeatureSink.FastInsert)

        feedback.pushDebugInfo("TimeFilterAlgorithm done !")

        # to get hold of the layer in post processing
        self.sink_id = sink_id

        return {"OUTPUT": sink_id}

    def postProcessAlgorithm(self, context, feedback):
        if self.RESULT_TYPE[self.params["OUTPUT_RESULT_TYPE"]] == "NORMAL":
            style_file = "style_route_duration.qml"
        else:
            style_file = "style_route_mode.qml"
        style_path = os.path.join(os.path.dirname(__file__), "resources", style_file)
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(
            style_path
        )
        return super().postProcessAlgorithm(context, feedback)

    def _processAlgorithmYieldSlices(self, parameters, context, feedback):
        """Yields slices to subdivide queries in smaller chunks"""

        locations_count = self.params["INPUT_LOCATIONS"].featureCount()

        slicing_size = 2
        slicing_count = math.ceil(locations_count / slicing_size)

        for i in range(slicing_count):
            for slice_ in super()._processAlgorithmYieldSlices(
                parameters, context, feedback
            ):
                slice_.update(
                    {
                        "loc_slice_start": i * slicing_size,
                        "loc_slice_end": (i + 1) * slicing_size,
                    }
                )
                yield slice_


class TimeMapSimpleAlgorithm(AlgorithmBase):
    _name = "time_map_simple"
    _displayName = tr("Time Map - Simple")
    _group = "Simplified"
    _groupId = "simple"
    _icon = resources.icon_time_map_simple
    _helpUrl = "http://docs.traveltimeplatform.com/reference/time-map/"
    _shortHelpString = tr(
        "This algorithms provides a simpified access to the time-map endpoint.\n\nPlease see the help on {url} for more details on how to use it."
    ).format(url=_helpUrl)

    SEARCH_TYPES = ["DEPARTURE", "ARRIVAL"]
    RESULT_TYPE = ["NORMAL", "UNION", "INTERSECTION"]

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
        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_RESULT_TYPE", tr("Result aggregation"), options=self.RESULT_TYPE
            ),
            help_text=tr(
                "NORMAL will return a polygon for each departure/arrival search. UNION will return the union of all polygons for all departure/arrivals searches. INTERSECTION will return the intersection of all departure/arrival searches."
            ),
        )

        # OUTPUT
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT", tr("Output layer"), type=QgsProcessing.TypeVectorPolygon
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo("Starting TimeMapSimpleAlgorithm...")

        # Configure common expressions inputs
        self.processAlgorithmConfigureParams(parameters, context, feedback)

        mode = self.SEARCH_TYPES[self.params["INPUT_SEARCH_TYPE"]]
        trnspt_type = TRANSPORTATION_TYPES[self.params["INPUT_TRNSPT_TYPE"]]
        result_type = self.RESULT_TYPE[self.params["OUTPUT_RESULT_TYPE"]]

        search_layer = self.params["INPUT_SEARCHES"].materialize(QgsFeatureRequest())

        sub_parameters = {
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

        feedback.pushDebugInfo("Calling subcommand with following parameters...")
        feedback.pushDebugInfo(str(sub_parameters))

        results = processing.run(
            "ttp_v4:time_map", sub_parameters, context=context, feedback=feedback
        )

        feedback.pushDebugInfo("Got results fom subcommand...")

        result_layer = results["OUTPUT"]

        # Configure output
        (sink, dest_id) = self.parameterAsSink(
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

        feedback.pushDebugInfo("TimeMapSimpleAlgorithm done !")

        # to get hold of the layer in post processing
        self.dest_id = dest_id
        self.result_type = result_type

        return {"OUTPUT": dest_id}

    def postProcessAlgorithm(self, context, feedback):
        retval = super().postProcessAlgorithm(context, feedback)
        if self.result_type == "UNION":
            style_file = "style_union.qml"
        elif self.result_type == "INTERSECTION":
            style_file = "style_intersection.qml"
        else:
            style_file = "style.qml"
        style_path = os.path.join(os.path.dirname(__file__), "resources", style_file)
        QgsProcessingUtils.mapLayerFromString(self.dest_id, context).loadNamedStyle(
            style_path
        )
        return retval


class TimeFilterSimpleAlgorithm(AlgorithmBase):
    _name = "time_filter_simple"
    _displayName = tr("Time Filter - Simple")
    _group = "Simplified"
    _groupId = "simple"
    _icon = resources.icon_time_filter_simple
    _helpUrl = "http://docs.traveltimeplatform.com/reference/time-filter/"
    _shortHelpString = tr(
        "This algorithms provides a simpified access to the time-filter endpoint.\n\nPlease see the help on {url} for more details on how to use it."
    ).format(url=_helpUrl)

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
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_LOCATIONS", tr("Locations"), [QgsProcessing.TypeVectorPoint]
            )
        )

        # OUTPUT
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT", tr("Output layer"), type=QgsProcessing.TypeVectorPoint
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo("Starting TimeFilterSimpleAlgorithm...")

        mode = self.SEARCH_TYPES[self.params["INPUT_SEARCH_TYPE"]]
        trnspt_type = TRANSPORTATION_TYPES[self.params["INPUT_TRNSPT_TYPE"]]

        search_layer = self.params["INPUT_SEARCHES"].materialize(QgsFeatureRequest())
        locations_layer = self.params["INPUT_LOCATIONS"].materialize(
            QgsFeatureRequest()
        )

        sub_parameters = {
            "INPUT_{}_SEARCHES".format(mode): search_layer,
            "INPUT_{}_TRNSPT_TYPE".format(mode): "'" + trnspt_type + "'",
            "INPUT_{}_TIME".format(mode): "'" + self.params["INPUT_TIME"] + "'",
            "INPUT_{}_TRAVEL_TIME".format(mode): str(
                self.params["INPUT_TRAVEL_TIME"] * 60
            ),
            "INPUT_{}_TRNSPT_WALKING_TIME".format(mode): str(
                self.params["INPUT_TRAVEL_TIME"] * 60
            ),
            "INPUT_LOCATIONS".format(mode): locations_layer,
            "OUTPUT": "memory:results",
        }

        feedback.pushDebugInfo("Calling subcommand with following parameters...")
        feedback.pushDebugInfo(str(sub_parameters))

        results = processing.run(
            "ttp_v4:time_filter", sub_parameters, context=context, feedback=feedback
        )

        feedback.pushDebugInfo("Got results fom subcommand...")

        result_layer = results["OUTPUT"]

        # Configure output
        (sink, dest_id) = self.parameterAsSink(
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

        feedback.pushDebugInfo("TimeFilterSimpleAlgorithm done !")

        # to get hold of the layer in post processing
        self.dest_id = dest_id

        return {"OUTPUT": dest_id}

    def postProcessAlgorithm(self, context, feedback):
        style_path = os.path.join(
            os.path.dirname(__file__), "resources", "style_filter.qml"
        )
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(
            style_path
        )
        return super().postProcessAlgorithm(context, feedback)


class RoutesSimpleAlgorithm(AlgorithmBase):
    _name = "routes_simple"
    _displayName = tr("Routes - Simple")
    _group = "Simplified"
    _groupId = "simple"
    _icon = resources.icon_routes_simple
    _helpUrl = "http://docs.traveltimeplatform.com/reference/routes/"
    _shortHelpString = tr(
        "This algorithms provides a simpified access to the routes endpoint.\n\nPlease see the help on {url} for more details on how to use it."
    ).format(url=_helpUrl)

    SEARCH_TYPES = ["DEPARTURE", "ARRIVAL"]
    RESULT_TYPE = ["NORMAL", "DETAILED"]

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
            QgsProcessingParameterFeatureSource(
                "INPUT_LOCATIONS", tr("Locations"), [QgsProcessing.TypeVectorPoint]
            )
        )

        # OUTPUT
        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_RESULT_TYPE", tr("Output style"), options=self.RESULT_TYPE
            ),
            help_text=tr(
                "Normal will return a simple linestring for each route. Detailed will return several segments for each type of transportation for each route."
            ),
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT", tr("Output layer"), type=QgsProcessing.TypeVectorPoint
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo("Starting RoutesSimpleAlgorithm...")

        # Configure common expressions inputs
        self.processAlgorithmConfigureParams(parameters, context, feedback)

        mode = self.SEARCH_TYPES[self.params["INPUT_SEARCH_TYPE"]]
        trnspt_type = TRANSPORTATION_TYPES[self.params["INPUT_TRNSPT_TYPE"]]
        search_layer = self.params["INPUT_SEARCHES"].materialize(QgsFeatureRequest())
        locations_layer = self.params["INPUT_LOCATIONS"].materialize(
            QgsFeatureRequest()
        )

        sub_parameters = {
            "INPUT_{}_SEARCHES".format(mode): search_layer,
            "INPUT_{}_TRNSPT_TYPE".format(mode): "'" + trnspt_type + "'",
            "INPUT_{}_TIME".format(mode): "'" + self.params["INPUT_TIME"] + "'",
            "INPUT_{}_TRNSPT_WALKING_TIME".format(mode): str(
                self.params["INPUT_TRAVEL_TIME"] * 60
            ),
            "INPUT_LOCATIONS": locations_layer,
            "OUTPUT_RESULT_TYPE": self.params["OUTPUT_RESULT_TYPE"],
            "OUTPUT": "memory:output",
        }

        feedback.pushDebugInfo("Calling subcommand with following parameters...")
        feedback.pushDebugInfo(str(sub_parameters))

        results = processing.run(
            "ttp_v4:routes", sub_parameters, context=context, feedback=feedback
        )

        feedback.pushDebugInfo("Got results fom subcommand...")

        result_layer = results["OUTPUT"]

        # Configure output
        (sink, dest_id) = self.parameterAsSink(
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

        feedback.pushDebugInfo("RoutesSimpleAlgorithm done !")

        # to get hold of the layer in post processing
        self.dest_id = dest_id
        self.result_type = result_type

        return {"OUTPUT": dest_id}

    def postProcessAlgorithm(self, context, feedback):
        if self.result_type == "NORMAL":
            style_file = "style_route_duration.qml"
        else:
            style_file = "style_route_mode.qml"
        style_path = os.path.join(os.path.dirname(__file__), "resources", style_file)
        QgsProcessingUtils.mapLayerFromString(self.dest_id, context).loadNamedStyle(
            style_path
        )
        return super().postProcessAlgorithm(context, feedback)


class GeocodingAlgorithmBase(AlgorithmBase):

    RESULT_TYPE = ["ALL", "BEST_MATCH"]

    def initAlgorithm(self, config):

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_DATA", tr("Input data"), [QgsProcessing.TypeVector]
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                "INPUT_COUNTRY",
                tr("Restrict to country"),
                optional=True,
                options=[c[1] for c in COUNTRIES],
            ),
            help_text=tr(
                "Only return the results that are within the specified country"
            ),
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_RESULT_TYPE", tr("Results type"), options=self.RESULT_TYPE
            ),
            help_text="ALL will return several results per input, corresponding to all potential matches returned by the API. BEST_MATCH will only return the best point.",
        )

        # Define output parameters
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT", tr("Output"), type=QgsProcessing.TypeVectorPoint
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo("Starting Geocoding...")

        # Configure common expressions inputs
        self.processAlgorithmConfigureParams(parameters, context, feedback)

        # Main implementation
        source_data = self.params["INPUT_DATA"]
        limit_country_chc = self.params["INPUT_COUNTRY"]
        limit_country = COUNTRIES[limit_country_chc][0] if limit_country_chc else None

        if source_data.featureCount() > 1:
            feedback.pushInfo(
                tr(
                    "Input layer has multiple features. The query will be executed in {} queries. This may have unexpected consequences on some parameters. Keep an eye on your API usage !"
                ).format(source_data.featureCount())
            )

        # NOTE : this is disabled, as geocoding queries don't count towards the quota
        # # Make sure we don't hit the API limit
        # self.processAlgorithmEnforceLimit(len(slices), parameters, context, feedback)

        # Configure output
        output_fields = QgsFields(source_data.fields())
        response_attributes = [
            "name",
            "label",
            "score",
            "house_number",
            "street",
            "region",
            "region_code",
            "neighbourhood",
            "county",
            "macroregion",
            "city",
            "country",
            "country_code",
            "continent",
        ]
        for attr in response_attributes:
            output_fields.append(
                QgsField("geocoded_" + attr, QVariant.String, "text", 255)
            )

        (sink, sink_id) = self.parameterAsSink(
            parameters, "OUTPUT", context, output_fields, QgsWkbTypes.Point, EPSG4326
        )

        results_by_id = {}

        for feature in source_data.getFeatures():

            # Set feature for expression context
            self.expressions_context.setFeature(feature)

            # Prepare the data
            source_data = self.params["INPUT_DATA"]
            limit_country_chc = self.params["INPUT_COUNTRY"]
            limit_country = (
                COUNTRIES[limit_country_chc][0] if limit_country_chc else None
            )

            params = self.processAlgorithmMakeGetParams(
                feature, source_data, parameters, context, feedback
            )
            if limit_country:
                params.update({"within.country": limit_country})

            # Make the query
            response_geojson = self.processAlgorithmMakeRequest(
                parameters, context, feedback, params=params
            )

            # Process the results
            result_type = self.RESULT_TYPE[self.params["OUTPUT_RESULT_TYPE"]]

            if result_type == "ALL":
                # We keep all results
                results = response_geojson["features"]
            elif result_type == "BEST_MATCH":
                # We only keep the result wit the best score
                results = sorted(
                    response_geojson["features"], key=lambda f: f["properties"]["score"]
                )[-1:]

            for result in results:
                newfeature = QgsFeature(output_fields)

                # Clone the existing attributes
                for i in range(len(source_data.fields())):
                    newfeature.setAttribute(i, feature.attribute(i))

                # Add our attributes
                props = result["properties"]
                for i, attr in enumerate(response_attributes):
                    output_fields.append(QgsField(attr, QVariant.String, "text", 255))
                    newfeature.setAttribute(
                        len(source_data.fields()) + i,
                        props[attr] if attr in props else None,
                    )

                # Add our geometry
                newfeature.setGeometry(
                    QgsPoint(
                        result["geometry"]["coordinates"][0],
                        result["geometry"]["coordinates"][1],
                    )
                )

                sink.addFeature(newfeature, QgsFeatureSink.FastInsert)

        # to get hold of the layer in post processing
        self.sink_id = sink_id

        return {"OUTPUT": sink_id}

    def processAlgorithmMakeGetParams(self, feature, parameters, context, feedback):
        """To be overriden by subclasses"""
        return {}


class GeocodingAlgorithm(GeocodingAlgorithmBase):
    url = "https://api.traveltimeapp.com/v4/geocoding/search"
    method = "GET"

    _name = "geocoding"
    _displayName = tr("Geocoding")
    _group = "Utilities"
    _groupId = "utils"
    _icon = resources.icon_geocoding
    _helpUrl = "https://docs.traveltimeplatform.com/reference/geocoding-search/"
    _shortHelpString = tr(
        "This algorithms provides access to the geocoding endpoint.\n\nPlease see the help on {url} for more details on how to use it."
    ).format(url=_helpUrl)

    def initAlgorithm(self, config):

        super().initAlgorithm(config)
        self.addParameter(
            QgsProcessingParameterExpression(
                "INPUT_QUERY_FIELD",
                tr("Search expression"),
                parentLayerParameterName="INPUT_DATA",
            ),
            help_text=tr(
                "The field containing the query to geocode. Can be an address, a postcode or a venue. For example SW1A 0AA or Victoria street, London. Providing a country or city the request will get you more accurate results"
            ),
        )
        self.addParameter(
            QgsProcessingParameterPoint(
                "INPUT_FOCUS", tr("Focus point"), optional=True
            ),
            help_text=tr(
                "This will prioritize results around this point. Note that this does not exclude results that are far away from the focus point"
            ),
        )

    def processAlgorithmMakeGetParams(
        self, feature, source_data, parameters, context, feedback
    ):
        focus_point = self.parameterAsPoint(parameters, "INPUT_FOCUS", context)
        focus_point_crs = self.parameterAsPointCrs(parameters, "INPUT_FOCUS", context)
        xform = QgsCoordinateTransform(
            focus_point_crs, EPSG4326, context.transformContext()
        )
        params = {"query": self.eval_expr("INPUT_QUERY_FIELD")}
        if focus_point:
            focus_point = xform.transform(focus_point)
            params.update({"focus.lat": focus_point.y(), "focus.lng": focus_point.x()})
        return params


class ReverseGeocodingAlgorithm(GeocodingAlgorithmBase):
    url = "https://api.traveltimeapp.com/v4/geocoding/reverse"
    method = "GET"

    _name = "reverse_geocoding"
    _displayName = tr("Reverse Geocoding")
    _group = "Utilities"
    _groupId = "utils"
    _icon = resources.icon_reverse_geocoding
    _helpUrl = "https://docs.traveltimeplatform.com/reference/geocoding-reverse/"
    _shortHelpString = tr(
        "This algorithms provides access to the reverse geocoding endpoint.\n\nPlease see the help on {url} for more details on how to use it."
    ).format(url=_helpUrl)

    def processAlgorithmMakeGetParams(
        self, feature, source_data, parameters, context, feedback
    ):
        xform = QgsCoordinateTransform(
            source_data.sourceCrs(), EPSG4326, context.transformContext()
        )
        focus_point = xform.transform(feature.geometry().asPoint())
        params = {"lat": focus_point.y(), "lng": focus_point.x()}
        return params


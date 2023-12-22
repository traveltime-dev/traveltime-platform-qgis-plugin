import collections
import datetime
import json

import requests
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsExpression,
    QgsExpressionContext,
    QgsLayerMetadata,
    QgsMapLayer,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputLayerDefinition,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtTest import QTest
from qgis.utils import iface

from .. import auth, cache, constants
from ..libraries import iso3166
from ..ui import AlgorithmDialogWithSkipLogic
from ..utils import log, throttler, tr

EPSG4326 = QgsCoordinateReferenceSystem("EPSG:4326")
THROTTLING_PER_SETTINGS = "PER_SETTINGS"
THROTTLING_DISABLED = "DISABLED"
THROTTLING_STRATEGIES = [THROTTLING_PER_SETTINGS, THROTTLING_DISABLED]
COUNTRIES = [(None, "-")] + list([(c.alpha2, c.name) for c in iso3166.countries])


class AlgorithmBase(QgsProcessingAlgorithm):
    """Base class for all processing algorithms (simple/advanced/utilities)"""

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
        self.parameters_help[advanced][parameter.description()] = help_text

        return super().addParameter(parameter, *args, **kwargs)

    def has_param(self, key):
        """Helper to check whether the algorithm has the specified param"""

        return any(p.name() == key for p in self.parameterDefinitions())

    def eval_expr(self, key):
        """Helper to evaluate an expression from the input.

        Do not forget to call self.expressions_context.setFeature(feature) before using this.
        """
        if key in self.params:
            return self.params[key].evaluate(self.expressions_context)
        else:
            return None

    def processAlgorithm(self, parameters, context, feedback):
        feedback.pushDebugInfo(
            "TravelTime Plugin Version : {}".format(constants.TTP_VERSION)
        )
        feedback.pushDebugInfo(
            "TravelTime Algorithm : {}".format(self.__class__.__name__)
        )
        # We save parameters to the instance to access it in postprocess
        self.raw_parameters = parameters
        return self.doProcessAlgorithm(parameters, context, feedback)

    def doProcessAlgorithm(self, parameters, context, feedback):
        raise NotImplemented("Method must be reimplemented by subclass")

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
            elif p.type() == "boolean":
                param = self.parameterAsBool(parameters, p.name(), context)
            elif p.type() == "string":
                param = self.parameterAsString(parameters, p.name(), context)
            elif p.type() == "ttp_datetime":
                param = self.parameterAsString(parameters, p.name(), context)
            elif p.type() == "field":
                param = self.parameterAsFields(parameters, p.name(), context)
            elif p.type() == "point":
                param = self.parameterAsPoint(parameters, p.name(), context)
                if param:
                    crs = self.parameterAsPointCrs(parameters, p.name(), context)
                    xform = QgsCoordinateTransform(
                        crs, EPSG4326, context.transformContext()
                    )
                    param = xform.transform(param)
            elif p.type() == "number":
                if p.dataType() == QgsProcessingParameterNumber.Type.Integer:
                    param = self.parameterAsInt(parameters, p.name(), context)
                else:
                    param = self.parameterAsDouble(parameters, p.name(), context)
            elif p.type() == "sink":
                # sinks need to be configured manually by the algorithms, as we must define output fields
                continue
            else:
                raise Exception(
                    "Parameter type {type} not supported [{name}]".format(
                        type=p.type(), name=p.name()
                    )
                )

            self.params[p.name()] = param

    def postProcessAlgorithm(self, context, feedback):
        """Sets the layer metadata"""

        if hasattr(self, "sink_id") and self.sink_id is not None:
            layer = QgsProcessingUtils.mapLayerFromString(self.sink_id, context)

            # Save the metadata
            metadata = QgsLayerMetadata()

            def serialize(o):
                """Serialize parameters, taking into account QGIS input/output types"""
                if isinstance(o, QgsMapLayer):
                    return o.dataUrl()
                elif isinstance(o, QgsProcessingOutputLayerDefinition):
                    return o.sink.valueAsString(QgsExpressionContext())[0]
                else:
                    feedback.pushWarning(
                        f"Could not serialize `{repr(o)}`, metadata will likely be incomplete."
                    )
                    return str(o)

            params_json = json.dumps(self.raw_parameters, default=serialize)
            params_readable = "\n".join(
                k + ": " + str(v) for k, v in json.loads(params_json).items()
            )

            metadata.setAbstract(
                "This layer was generated using the '{}' algorithm from the TravelTime plugin version {}. The following parameters were used : \n{}".format(
                    self.displayName(), constants.TTP_VERSION, params_readable
                )
            )
            metadata.setKeywords(
                {
                    "TTP_VERSION": [constants.TTP_VERSION],
                    "TTP_ALGORITHM": [self.id()],
                    "TTP_PARAMS": [params_json],
                }
            )
            layer.setMetadata(metadata)

        return super().postProcessAlgorithm(context, feedback)

    def createInstance(self):
        return self.__class__()

    def createCustomParametersWidget(self, parent):
        if parent is None:
            parent = iface.mainWindow()
        return AlgorithmDialogWithSkipLogic(self, parent=parent)

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
                    "\n<b>{}</b>: {}".format(key, val or "-")
                    for key, val in self.parameters_help[False].items()
                ]
            )
        if self.parameters_help[True]:
            help_string += "<h2>Advanced parameters description</h2>" + "".join(
                [
                    "\n<b>{}</b>: {}".format(key, val or "-")
                    for key, val in self.parameters_help[True].items()
                ]
            )
        return help_string


class ProcessingAlgorithmBase(AlgorithmBase):
    """Base class for algorithms that do actuall processing (advanced/utilities)"""

    method = "POST"
    accept_header = "application/json"
    output_aliases = {}

    def initAlgorithm(self, config):
        self.addParameter(
            QgsProcessingParameterEnum(
                "INPUT_THROTTLING_STRATEGY",
                "Throttling strategy",
                THROTTLING_STRATEGIES,
                defaultValue=THROTTLING_STRATEGIES.index(THROTTLING_PER_SETTINGS),
            ),
            advanced=True,
            help_text=tr(
                "Set which throttling strategy to use : either as per settings, or disabled."
            ),
        )

    def prepareAlgorithm(self, parameters, context, feedback):
        # Get the API KEY. This must be done here, so it's run in the main thread, as it may require GUI (if master
        # password is not set).
        self.APP_ID, self.API_KEY = auth.get_app_id_and_api_key()

        if not self.APP_ID or not self.API_KEY:
            feedback.reportError(
                tr(
                    "Could not retrieve APP_ID and/or API_KEY. Make sure they are correctly defined in the plugin's settings."
                ),
                fatalError=True,
            )
            return False

        return True

    def processAlgorithmComputeSearchCountForThrottling(self, data):
        """Returns how many searches the request will take for throttling"""

        # By default, we count 1 search
        return 1

    def processAlgorithmMakeRequest(
        self, parameters, context, feedback, data=None, params={}
    ):
        """Helper method to check the API limits and make an authenticated request"""

        # Stop on user request
        if feedback.isCanceled():
            feedback.reportError(
                tr("Algorithm was cancelled by the user."), fatalError=True
            )
            raise QgsProcessingException("Algorithm was cancelled by the user.")

        json_data = json.dumps(data)

        # Get API key
        if not self.APP_ID or not self.API_KEY:
            feedback.reportError(
                tr(
                    "You need a TravelTime API key to make requests. Please head to {} to obtain one, and enter it in the plugin's setting dialog."
                ).format("http://docs.traveltimeplatform.com/overview/getting-keys/"),
                fatalError=True,
            )
            raise QgsProcessingException("App ID or api key not set")

        headers = {
            "Content-type": "application/json",
            "Accept": self.accept_header,
            "User-Agent": "QGIS / {} / {}".format(
                Qgis.QGIS_VERSION_INT, constants.TTP_VERSION
            ),
            "X-Application-Id": self.APP_ID,
            "X-Api-Key": self.API_KEY,
        }

        endpoint = QSettings().value(
            "traveltime_platform/custom_endpoint", constants.DEFAULT_ENDPOINT, type=str
        )
        full_url = endpoint + self.url

        feedback.pushDebugInfo("Making request to API endpoint...")
        print_query = bool(QSettings().value("traveltime_platform/log_calls", False))
        if print_query:
            headers_for_logs = dict(headers)
            if headers_for_logs["X-Application-Id"]:
                headers_for_logs["X-Application-Id"] = "*hidden*"
            if headers_for_logs["X-Api-Key"]:
                headers_for_logs["X-Api-Key"] = "*hidden*"

            log("Making request")
            log("url: {}".format(full_url))
            log("headers: {}".format(headers_for_logs))
            log("params: {}".format(str(params)))
            log("data: {}".format(json_data))

        disable_https = QSettings().value(
            "traveltime_platform/disable_https", False, type=bool
        )
        if disable_https:
            feedback.pushInfo(
                tr(
                    "Warning ! HTTPS certificate verification is disabled. This means all data sent to the API can potentially be intercepted by an attacker."
                )
            )

        request = requests.Request(
            self.method,
            full_url,
            data=json_data,
            params=params,
            headers=headers,
        ).prepare()

        cached = cache.instance.cached_requests.cache.has_key(
            cache.instance.cached_requests.cache.create_key(request)
        )
        throttling_disabled = (
            THROTTLING_STRATEGIES[self.params["INPUT_THROTTLING_STRATEGY"]]
            == THROTTLING_DISABLED
        )
        if not throttling_disabled and not cached:
            # Throttling the query if needed
            searches_count = self.processAlgorithmComputeSearchCountForThrottling(data)
            throttling, recent_seaches_count = throttler.throttle_query(searches_count)

            if throttling > 0:
                feedback.pushWarning(
                    tr(
                        "Throttling next {} searches for {}s ({} searches made in the last {}s)"
                    ).format(
                        searches_count,
                        round(throttling),
                        recent_seaches_count,
                        throttler.DURATION,
                    )
                )
                wait_until = datetime.datetime.now() + datetime.timedelta(
                    seconds=throttling
                )
                while datetime.datetime.now() <= wait_until:
                    if feedback.isCanceled():
                        raise QgsProcessingException("Canceled by user") from None
                    QTest.qWait(100)

        try:
            response = cache.instance.cached_requests.send(
                request, verify=not disable_https
            )
        except requests.exceptions.RequestException as e:
            feedback.reportError(
                tr(
                    "Error while connecting to the API server. See log for more details."
                ),
                fatalError=True,
            )
            log(e)
            raise QgsProcessingException(
                "Error while connecting to the API server"
            ) from None

        try:
            response_data = json.loads(response.text)
        except ValueError as e:
            feedback.reportError(
                tr("Could not decode response. See log for more details."),
                fatalError=True,
            )
            log(e)
            raise QgsProcessingException("Could not decode response") from None

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            nice_info = "\n".join(
                "\t{}:\t{}".format(k, v)
                for k, v in response_data["additional_info"].items()
            )
            feedback.reportError(
                tr(
                    "Received error from the API.\nError code : {}\nDescription : {}\nSee : {}\nAddtionnal info :\n{}"
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

        if response.from_cache:
            feedback.pushDebugInfo("Got response from cache...")
        else:
            feedback.pushDebugInfo("Got response from API endpoint...")
            QSettings().setValue(
                "traveltime_platform/current_count",
                int(QSettings().value("traveltime_platform/current_count", 0)) + 1,
            )

        if print_query:
            log("Got response")
            log("status: {}".format(response.status_code))
            log("reason: {}".format(response.reason))
            log("text: {}".format(response.text))

        return response_data

    def postProcessAlgorithm(self, context, feedback):
        """Sets the field aliases"""

        if hasattr(self, "sink_id") and self.sink_id is not None:
            layer = QgsProcessingUtils.mapLayerFromString(self.sink_id, context)

            # Set field aliases
            for field_name, alias in self.output_aliases.items():
                field_idx = layer.fields().indexOf(field_name)
                if field_idx == -1:
                    # field does not exist in ouput, we skip it
                    continue
                layer.setFieldAlias(field_idx, alias)

        return super().postProcessAlgorithm(context, feedback)

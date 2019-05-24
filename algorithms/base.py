import requests
import json
import os
import collections
from qgis.PyQt.QtCore import QSettings

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterNumber,
    QgsProcessingException,
    QgsProcessingParameterDefinition,
    QgsCoordinateReferenceSystem,
    QgsExpression,
)

from ..libraries import requests_cache
from ..libraries import iso3166

from .. import auth

from ..utils import tr, log


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
    # Regular
    cache_name="ttp_cache",
    backend="memory",
    # # Persisting (use for development, to avoid hitting API limit)
    # cache_name=os.path.join(os.path.dirname(os.path.dirname(__file__)), "cachefile"),
    # backend="sqlite",
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


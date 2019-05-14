import requests
import time
import json
import os
import math

from qgis.PyQt.QtCore import QVariant, QSettings
from qgis.PyQt.QtWidgets import QMessageBox

from qgis.core import (QgsMessageLog,
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
                       QgsWkbTypes,
                       QgsCoordinateReferenceSystem,
                       QgsPoint,
                       QgsLineString,
                       QgsFields,
                       QgsField,
                       QgsFeature,
                       QgsGeometry,
                       QgsExpression,
                       QgsFeatureRequest,
                       QgsProcessingUtils)

import processing

from .libraries import requests_cache

from . import resources
from . import auth
from . import utils
from . import parameters
from .utils import tr


EPSG4326 = QgsCoordinateReferenceSystem("EPSG:4326")
TRANSPORTATION_TYPES = ['cycling', 'driving', 'driving+train', 'public_transport', 'walking', 'coach', 'bus', 'train', 'ferry', 'driving+ferry', 'cycling+ferry']

cached_requests = requests_cache.core.CachedSession(
    # Regular
    cache_name="ttp_cache",
    backend="memory",
    # # Persisting (use for development, to avoid hitting API limit)
    # cache_name=os.path.join(os.path.dirname(__file__), 'cachefile'),
    # backend="sqlite",
    expire_after=86400,
    allowable_methods=('GET', 'POST')
)


class AlgorithmBase(QgsProcessingAlgorithm):
    """Base class for all processing algorithms"""

    def addAdvancedParamter(self, parameter, *args, **kwargs):
        """Helper to add advanced parameters"""
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        return self.addParameter(parameter, *args, **kwargs)

    def eval_expr(self, key):
        """Helper to evaluate an expression from the input.

        Do not forget to call self.expressions_context.setFeature(feature) before using this."""
        if key in self.expressions:
            return self.expressions[key].evaluate(self.expressions_context)
        else:
            return None

    def processAlgorithmConfigureExpressionInputs(self, parameters, context, feedback):
        """Helper method that sets up all expressions parameter"""
        self.expressions_context = self.createExpressionContext(parameters, context)
        self.expressions = {}
        for PARAM in [p.name() for p in self.parameterDefinitions() if p.type() == 'expression']:
            self.expressions[PARAM] = QgsExpression(self.parameterAsExpression(parameters, PARAM, context))
            self.expressions[PARAM].prepare(self.expressions_context)

    def processAlgorithmMakeRequest(self, data, parameters, context, feedback):
        """Helper method to check the API limits and make an authenticated request"""

        json_data = json.dumps(data)

        # Get API key
        APP_ID, API_KEY = auth.get_app_id_and_api_key()
        if not APP_ID or not API_KEY:
            feedback.reportError(tr('You need a Travel Time Platform API key to make requests. Please head to {} to obtain one, and enter it in the plugin\'s setting dialog.').format('http://docs.traveltimeplatform.com/overview/getting-keys/'), fatalError=True)
            raise QgsProcessingException('App ID or api key not set')

        headers = {
            'Content-type': 'application/json',
            'Accept': self.accept_header,
            'X-Application-Id': APP_ID,
            'X-Api-Key': API_KEY,
        }

        feedback.pushDebugInfo('Checking API limit warnings...')
        s = QSettings()
        retries = 10
        for i in range(retries):
            enabled = bool(s.value('travel_time_platform/warning_enabled', True))
            count = int(s.value('travel_time_platform/current_count', 0)) + 1
            limit = int(s.value('travel_time_platform/warning_limit', 10)) + 1
            if enabled and count >= limit:
                if i == 0:
                    feedback.reportError(tr('WARNING : API usage warning limit reached !'))
                    feedback.reportError(tr('To continue, disable or increase the limit in the plugin settings, or reset the queries counter. Now is your chance to do the changes.'))
                feedback.reportError(tr('Execution will resume in 10 seconds (retry {} out of {})').format(i+1, retries))
                time.sleep(10)
            else:
                if enabled:
                    feedback.pushInfo(tr('API usage warning limit not reached yet ({} queries remaining)...').format(limit-count))
                else:
                    feedback.pushInfo(tr('API usage warning limit disabled...'))
                break
        else:
            feedback.reportError(tr('Execution canceled because of API limit warning.'), fatalError=True)
            raise QgsProcessingException('API usage limit warning')

        feedback.pushDebugInfo('Making request to API endpoint...')
        print_query = bool(s.value('travel_time_platform/log_calls', False))
        if print_query:
            QgsMessageLog.logMessage("Making request", 'TimeTravelPlatform')
            QgsMessageLog.logMessage("url: {}".format(self.url), 'TimeTravelPlatform')
            QgsMessageLog.logMessage("headers: {}".format(headers), 'TimeTravelPlatform')
            QgsMessageLog.logMessage("data: {}".format(json_data), 'TimeTravelPlatform')

        try:

            response = cached_requests.post(self.url, data=json_data, headers=headers)

            if response.from_cache:
                feedback.pushDebugInfo('Got response from cache...')
            else:
                feedback.pushDebugInfo('Got response from API endpoint...')
                s.setValue('travel_time_platform/current_count', int(s.value('travel_time_platform/current_count', 0)) + 1)

            if print_query:
                QgsMessageLog.logMessage("Got response", 'TimeTravelPlatform')
                QgsMessageLog.logMessage("status: {}".format(response.status_code), 'TimeTravelPlatform')
                QgsMessageLog.logMessage("reason: {}".format(response.reason), 'TimeTravelPlatform')
                QgsMessageLog.logMessage("text: {}".format(response.text), 'TimeTravelPlatform')

            response_data = json.loads(response.text)
            response.raise_for_status()

            return response_data

        except requests.exceptions.HTTPError as e:
            nice_info = '\n'.join('\t{}:\t{}'.format(k,v) for k,v in response_data['additional_info'].items())
            feedback.reportError(tr('Recieved error from the API.\nError code : {}\nDescription : {}\nSee : {}\nAddtionnal info :\n{}').format(response_data['error_code'],response_data['description'],response_data['documentation_link'],nice_info), fatalError=True)
            feedback.reportError(tr('See log for more details.'), fatalError=True)
            QgsMessageLog.logMessage(str(e), 'TimeTravelPlatform')
            raise QgsProcessingException('Got error {} form API'.format(response.status_code)) from None
        except requests.exceptions.RequestException as e:
            feedback.reportError(tr('Could not connect to the API. See log for more details.'), fatalError=True)
            QgsMessageLog.logMessage(str(e), 'TimeTravelPlatform')
            raise QgsProcessingException('Could not connect to API') from None
        except ValueError as e:
            feedback.reportError(tr('Could not decode response. See log for more details.'), fatalError=True)
            QgsMessageLog.logMessage(str(e), 'TimeTravelPlatform')
            raise QgsProcessingException('Could not decode response') from None

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
        return self._shortHelpString


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

        for DEPARR in ['DEPARTURE', 'ARRIVAL']:
            self.addParameter(
                QgsProcessingParameterFeatureSource('INPUT_'+DEPARR+'_SEARCHES',
                                                    '{} / Searches'.format(DEPARR.title()),
                                                    [QgsProcessing.TypeVectorPoint],
                                                    optional=True, )
            )
            self.addParameter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_ID',
                                                 '{} / ID'.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="'"+DEPARR.lower()+"_searches_' || $id",
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )
            # Transportation
            self.addParameter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_TRNSPT_TYPE',
                                                 '{} / Transportation / type'.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="'public_transport'",
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )
            self.addAdvancedParamter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_TRNSPT_PT_CHANGE_DELAY',
                                                 '{} / Transportation / change delay'.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="0",
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )
            self.addAdvancedParamter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_TRNSPT_WALKING_TIME',
                                                 '{} / Transportation / walking time'.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="900",
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )
            self.addAdvancedParamter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_TRNSPT_DRIVING_TIME_TO_STATION',
                                                 '{} / Transportation / driving time to station'.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="1800",
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )
            self.addAdvancedParamter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_TRNSPT_PARKING_TIME',
                                                 '{} / Transportation / parking time'.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="300",
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )
            self.addAdvancedParamter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_TRNSPT_BOARDING_TIME',
                                                 '{} / Transportation / boarding time'.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="0",
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )
            self.addAdvancedParamter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_RANGE_WIDTH',
                                                 '{} / Search range width '.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="null",
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )
            self.addParameter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_TIME',
                                                 '{} / Time'.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="'{}'".format(utils.now_iso()),
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )
            self.addParameter(
                QgsProcessingParameterExpression('INPUT_'+DEPARR+'_TRAVEL_TIME',
                                                 '{} / Travel time'.format(DEPARR.title()),
                                                 optional=True,
                                                 defaultValue="900",
                                                 parentLayerParameterName='INPUT_'+DEPARR+'_SEARCHES',)
            )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo('Starting {}...'.format(self.__class__.__name__))

        # Configure common expressions inputs
        self.processAlgorithmConfigureExpressionInputs(parameters, context, feedback)

        # Main implementation
        source_departure = self.parameterAsSource(parameters, 'INPUT_DEPARTURE_SEARCHES', context)
        source_arrival = self.parameterAsSource(parameters, 'INPUT_ARRIVAL_SEARCHES', context)

        source_departure_count = source_departure.featureCount() if source_departure else 0
        source_arrival_count = source_arrival.featureCount() if source_arrival else 0

        slicing_size = 10
        slicing_count = math.ceil(max(source_departure_count, source_arrival_count) / slicing_size)

        if slicing_count > 1:
            feedback.pushInfo(tr('Input layers have more than {} features. The query will be executed in {} queries. This may have unexpected consequences on some parameters. Keep an eye on your API usage !').format(slicing_size, slicing_count))

        results = []

        for slicing_i in range(slicing_count):
            slicing_start = slicing_i * slicing_size
            slicing_end = (slicing_i + 1) * slicing_size

            # Prepare the data
            data = {}
            for DEPARR, source in [('DEPARTURE', source_departure), ('ARRIVAL', source_arrival)]:
                deparr = DEPARR.lower()
                if source:
                    feedback.pushDebugInfo('Loading {} searches features...'.format(deparr))
                    data[deparr+'_searches'] = []
                    xform = QgsCoordinateTransform(source.sourceCrs(), EPSG4326, context.transformContext())
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

                        data[deparr+'_searches'].append({
                            "id": self.eval_expr('INPUT_'+DEPARR+'_ID'),
                            "coords": {
                                "lat": geometry.asPoint().y(),
                                "lng": geometry.asPoint().x(),
                            },
                            "transportation": {
                                "type": self.eval_expr('INPUT_'+DEPARR+'_TRNSPT_TYPE'),
                                "pt_change_delay": self.eval_expr('INPUT_'+DEPARR+'_TRNSPT_PT_CHANGE_DELAY'),
                                "walking_time": self.eval_expr('INPUT_'+DEPARR+'_TRNSPT_WALKING_TIME'),
                                "driving_time_to_station": self.eval_expr('INPUT_'+DEPARR+'_TRNSPT_DRIVING_TIME_TO_STATION'),
                                "parking_time": self.eval_expr('INPUT_'+DEPARR+'_TRNSPT_PARKING_TIME'),
                                "boarding_time": self.eval_expr('INPUT_'+DEPARR+'_TRNSPT_BOARDING_TIME'),
                            },
                            deparr+'_time': self.eval_expr('INPUT_'+DEPARR+'_TIME'),
                            "travel_time": self.eval_expr('INPUT_'+DEPARR+'_TRAVEL_TIME'),
                            # TODO : allow to edit properties
                            'properties': self.search_properties
                        })

                        # # Update the progress bar
                        # feedback.setProgress(int(current * total))

            # Remix the data as needed
            data = self.processAlgorithmRemixData(data, parameters, context, feedback)

            # Make the query
            response_data = self.processAlgorithmMakeRequest(data, parameters, context, feedback)

            results += response_data['results']

        feedback.pushDebugInfo('Loading response to layer...')

        # Configure output
        return self.processAlgorithmOutput(results, parameters, context, feedback)


    def processAlgorithmRemixData(self, data, parameters, context, feedback):
        """To be overriden by subclasses : allow to edit the data object before sending to the API"""
        return data

    def processAlgorithmOutput(self, results, parameters, context, feedback):
        """To be overriden by subclasses : manages the output"""
        return None


class TimeMapAlgorithm(SearchAlgorithmBase):
    url = 'https://api.traveltimeapp.com/v4/time-map'
    accept_header = 'application/vnd.wkt+json'

    _name = 'time_map'
    _displayName = 'Time Map'
    _group = 'Advanced'
    _groupId = 'advanced'
    _icon = resources.icon_time_map_advanced
    _helpUrl = 'http://docs.traveltimeplatform.com/reference/time-map/'
    _shortHelpString = tr("This algorithms allows to use the time-map endpoint from the Travel Time Platform API.\n\nIt matches exactly the endpoint data structure. Please see the help on {url} for more details on how to use it.\n\nConsider using the other algorithms as they may be easier to work with.").format(url=_helpUrl)

    def initAlgorithm(self, config):

        # Define all common DEPARTURE and ARRIVAL parameters
        super().initAlgorithm(config)

        # Define additional input parameters
        self.addParameter(
            QgsProcessingParameterBoolean('INPUT_CALC_UNION',
                                          tr('Compute union aggregation'),
                                          optional=True,
                                          defaultValue=False)
        )
        self.addParameter(
            QgsProcessingParameterBoolean('INPUT_CALC_INTER',
                                          tr('Compute intersection aggregation'),
                                          optional=True,
                                          defaultValue=False)
        )

        # Define output parameters
        self.addParameter(
            QgsProcessingParameterFeatureSink('OUTPUT_SEARCHES',
                                              tr('Output - searches layer'),
                                              type=QgsProcessing.TypeVectorPolygon, )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink('OUTPUT_UNION',
                                              tr('Output - union layer'),
                                              type=QgsProcessing.TypeVectorPolygon, )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink('OUTPUT_INTER',
                                              tr('Output - intersection layer'),
                                              type=QgsProcessing.TypeVectorPolygon, )
        )

    def processAlgorithmRemixData(self, data, parameters, context, feedback):
        """To be overriden by subclasses : allow to edit the data object before sending to the API"""

        compute_union = self.parameterAsBool(parameters, 'INPUT_CALC_UNION', context)
        compute_inter = self.parameterAsBool(parameters, 'INPUT_CALC_INTER', context)

        if compute_union or compute_inter:
            search_ids = []
            for deparr in ['departure','arrival']:
                if deparr+'_searches' in data:
                    for d in data[deparr+'_searches']:
                        search_ids.append(d['id'])
            if compute_union:
                data['unions'] = [{'id': 'union_all', 'search_ids': search_ids}]
            if compute_inter:
                data['intersections'] = [{'id': 'intersection_all', 'search_ids': search_ids}]

        return data

    def processAlgorithmOutput(self, results, parameters, context, feedback):
        output_fields = QgsFields()
        output_fields.append(QgsField('id', QVariant.String, 'text', 255))
        output_fields.append(QgsField('properties', QVariant.String, 'text', 255))

        (sink, sink_id) = self.parameterAsSink(parameters, 'OUTPUT_SEARCHES', context, output_fields, QgsWkbTypes.MultiPolygon, EPSG4326)
        (sink_union, sink_union_id) = self.parameterAsSink(parameters, 'OUTPUT_UNION', context, output_fields, QgsWkbTypes.MultiPolygon, EPSG4326)
        (sink_inter, sink_inter_id) = self.parameterAsSink(parameters, 'OUTPUT_INTER', context, output_fields, QgsWkbTypes.MultiPolygon, EPSG4326)

        for result in results:
            feature = QgsFeature(output_fields)
            feature.setAttribute(0, result['search_id'])
            feature.setAttribute(1, json.dumps(result['properties']))
            feature.setGeometry(QgsGeometry.fromWkt(result['shape']))

            # Add a feature in the sink
            if result['search_id'] == 'union_all':
                sink_union.addFeature(feature, QgsFeatureSink.FastInsert)
            elif result['search_id'] == 'intersection_all':
                sink_inter.addFeature(feature, QgsFeatureSink.FastInsert)
            else:
                sink.addFeature(feature, QgsFeatureSink.FastInsert)

        feedback.pushDebugInfo('TimeMapAlgorithm done !')

        # to get hold of the layer in post processing
        self.sink_id = sink_id
        self.sink_union_id = sink_union_id
        self.sink_inter_id = sink_inter_id

        return {
            'OUTPUT_SEARCHES': sink_id,
            'OUTPUT_UNION': sink_union_id,
            'OUTPUT_INTER': sink_inter_id,
        }

    def postProcessAlgorithm(self, context, feedback):
        retval = super().postProcessAlgorithm(context, feedback)
        style_path = os.path.join(os.path.dirname(__file__), 'resources', 'style_union.qml')
        QgsProcessingUtils.mapLayerFromString(self.sink_union_id, context).loadNamedStyle(style_path)
        style_path = os.path.join(os.path.dirname(__file__), 'resources', 'style_intersection.qml')
        QgsProcessingUtils.mapLayerFromString(self.sink_inter_id, context).loadNamedStyle(style_path)
        style_path = os.path.join(os.path.dirname(__file__), 'resources', 'style.qml')
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(style_path)
        return retval


class TimeFilterAlgorithm(SearchAlgorithmBase):
    url = 'https://api.traveltimeapp.com/v4/time-filter'
    accept_header = 'application/json'
    # search_properties = ["travel_time", "distance", "distance_breakdown", "fares", "route"]
    search_properties = ["travel_time", "distance", "distance_breakdown", "route"]

    _name = 'time_filter'
    _displayName = 'Time Filter'
    _group = 'Advanced'
    _groupId = 'advanced'
    _icon = resources.icon_time_filter_advanced
    _helpUrl = 'http://docs.traveltimeplatform.com/reference/time-filter/'
    _shortHelpString = tr("This algorithms allows to use the time-filter endpoint from the Travel Time Platform API.\n\nIt matches exactly the endpoint data structure. Please see the help on {url} for more details on how to use it.\n\nConsider using the other algorithms as they may be easier to work with.").format(url=_helpUrl)

    def initAlgorithm(self, config):

        # Define all common DEPARTURE and ARRIVAL parameters
        super().initAlgorithm(config)

        # Define additional input parameters
        self.addParameter(
            QgsProcessingParameterFeatureSource('INPUT_LOCATIONS',
                                                tr('Locations'),
                                                [QgsProcessing.TypeVectorPoint],
                                                optional=False, )
        )
        self.addParameter(
            QgsProcessingParameterExpression('INPUT_LOCATIONS_ID',
                                             'Locations ID',
                                             optional=True,
                                             defaultValue="'locations_' || $id",
                                             parentLayerParameterName='INPUT_LOCATIONS',)
        )

        # Define output parameters
        self.addParameter(
            QgsProcessingParameterFeatureSink('OUTPUT',
                                              tr('Results'),
                                              type=QgsProcessing.TypeVectorPoint, )
        )

    def processAlgorithmRemixData(self, data, parameters, context, feedback):
        locations = self.parameterAsSource(parameters, 'INPUT_LOCATIONS', context)

        # Prepare location data (this is the same for all the slices)
        data['locations'] = []
        xform = QgsCoordinateTransform(locations.sourceCrs(), EPSG4326, context.transformContext())
        for feature in locations.getFeatures():
            # Set feature for expression context
            self.expressions_context.setFeature(feature)
            geometry = feature.geometry()
            geometry.transform(xform)
            data['locations'].append({
                'id': self.eval_expr('INPUT_LOCATIONS_ID'),
                'coords': {"lat": geometry.asPoint().y(), "lng": geometry.asPoint().x(), }
            })

        # Currently, the API requires all geoms to be passed in the locations parameter
        # and refers to them using departure_location_id and arrival_location_ids in the
        # departure_searches definition.
        # Here we remix the data array to conform to this data model.
        all_locations_ids = [l['id'] for l in data['locations']]
        if 'departure_searches' in data:
            for departure_search in data['departure_searches']:
                data['locations'].append({
                    'id': departure_search['id'],
                    'coords': departure_search['coords'],
                })
                del departure_search['coords']
                departure_search['departure_location_id'] = departure_search['id']
                departure_search['arrival_location_ids'] = all_locations_ids
        if 'arrival_searches' in data:
            for arrival_search in data['arrival_searches']:
                data['locations'].append({
                    'id': arrival_search['id'],
                    'coords': arrival_search['coords'],
                })
                del arrival_search['coords']
                arrival_search['arrival_location_id'] = arrival_search['id']
                arrival_search['departure_location_ids'] = all_locations_ids

        return data

    def processAlgorithmOutput(self, results, parameters, context, feedback):
        locations = self.parameterAsSource(parameters, 'INPUT_LOCATIONS', context)

        output_fields = locations.fields()
        output_fields.append(QgsField('search_id', QVariant.String, 'text', 255))
        output_fields.append(QgsField('reachable', QVariant.Int, 'int', 255))
        output_fields.append(QgsField('properties', QVariant.String, 'text', 255))

        output_crs = locations.sourceCrs()
        output_type = locations.wkbType()

        QgsWkbTypes.MultiPolygon

        (sink, sink_id) = self.parameterAsSink(parameters, 'OUTPUT', context, output_fields, output_type, output_crs)

        def clone_feature(id_):
            """Returns a feature cloned from the locations layer"""
            id_expr = self.parameterAsString(parameters, 'INPUT_LOCATIONS_ID', context)
            expression_ctx = self.createExpressionContext(parameters, context)
            expression = QgsExpression("{} = '{}'".format(id_expr, id_))
            return utils.clone_feature(QgsFeatureRequest(expression, expression_ctx), locations, output_fields)

        for result in results:
            for location in result['locations']:
                feature = clone_feature(location['id'])
                feature.setAttribute(len(output_fields)-3, result['search_id'])
                feature.setAttribute(len(output_fields)-2, 1)
                feature.setAttribute(len(output_fields)-1, json.dumps(location['properties']))
                sink.addFeature(feature, QgsFeatureSink.FastInsert)
            for id_ in result['unreachable']:
                feature = clone_feature(id_)
                feature.setAttribute(len(output_fields)-3, result['search_id'])
                feature.setAttribute(len(output_fields)-2, 0)
                feature.setAttribute(len(output_fields)-1, None)
                sink.addFeature(feature, QgsFeatureSink.FastInsert)

        feedback.pushDebugInfo('TimeFilterAlgorithm done !')

        # to get hold of the layer in post processing
        self.sink_id = sink_id

        return {
            'OUTPUT_RESULTS': sink_id,
        }

    def postProcessAlgorithm(self, context, feedback):
        style_path = os.path.join(os.path.dirname(__file__), 'resources', 'style_filter.qml')
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(style_path)
        return super().postProcessAlgorithm(context, feedback)


class RoutesAlgorithm(SearchAlgorithmBase):
    url = 'https://api.traveltimeapp.com/v4/routes'
    accept_header = 'application/json'
    # search_properties = ["travel_time", "distance", "route", "fares"]
    search_properties = ["travel_time", "distance", "route"]

    _name = 'routes'
    _displayName = 'Routes'
    _group = 'Advanced'
    _groupId = 'advanced'
    _icon = resources.icon_routes_advanced
    _helpUrl = 'http://docs.traveltimeplatform.com/reference/routes/'
    _shortHelpString = tr("This algorithms allows to use the routes endpoint from the Travel Time Platform API.\n\nIt matches exactly the endpoint data structure. Please see the help on {url} for more details on how to use it.\n\nConsider using the other algorithms as they may be easier to work with.").format(url=_helpUrl)

    def initAlgorithm(self, config):

        # Define all common DEPARTURE and ARRIVAL parameters
        super().initAlgorithm(config)

        # Remove unused parameters
        self.removeParameter('INPUT_DEPARTURE_TRAVEL_TIME')
        self.removeParameter('INPUT_ARRIVAL_TRAVEL_TIME')

        # Define additional input parameters
        self.addParameter(
            QgsProcessingParameterFeatureSource('INPUT_LOCATIONS',
                                                tr('Locations'),
                                                [QgsProcessing.TypeVectorPoint],
                                                optional=False, )
        )
        self.addParameter(
            QgsProcessingParameterExpression('INPUT_LOCATIONS_ID',
                                             'Locations ID',
                                             optional=True,
                                             defaultValue="'locations_' || $id",
                                             parentLayerParameterName='INPUT_LOCATIONS',)
        )

        # Define output parameters
        self.addParameter(
            QgsProcessingParameterFeatureSink('OUTPUT_NORMAL',
                                              tr('Routes'),
                                              type=QgsProcessing.TypeVectorLine, )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink('OUTPUT_DETAILED',
                                              tr('Detailed route'),
                                              type=QgsProcessing.TypeVectorLine, )
        )

    def processAlgorithmRemixData(self, data, parameters, context, feedback):
        locations = self.parameterAsSource(parameters, 'INPUT_LOCATIONS', context)

        # Prepare location data (this is the same for all the slices)
        data['locations'] = []
        xform = QgsCoordinateTransform(locations.sourceCrs(), EPSG4326, context.transformContext())
        for feature in locations.getFeatures():
            # Set feature for expression context
            self.expressions_context.setFeature(feature)
            geometry = feature.geometry()
            geometry.transform(xform)
            data['locations'].append({
                'id': self.eval_expr('INPUT_LOCATIONS_ID'),
                'coords': {"lat": geometry.asPoint().y(), "lng": geometry.asPoint().x(), }
            })

        # Currently, the API requires all geoms to be passed in the locations parameter
        # and refers to them using departure_location_id and arrival_location_ids in the
        # departure_searches definition.
        # Here we remix the data array to conform to this data model.
        all_locations_ids = [l['id'] for l in data['locations']]
        if 'departure_searches' in data:
            for departure_search in data['departure_searches']:
                data['locations'].append({
                    'id': departure_search['id'],
                    'coords': departure_search['coords'],
                })
                del departure_search['coords']
                del departure_search['travel_time']
                departure_search['departure_location_id'] = departure_search['id']
                departure_search['arrival_location_ids'] = all_locations_ids
        if 'arrival_searches' in data:
            for arrival_search in data['arrival_searches']:
                data['locations'].append({
                    'id': arrival_search['id'],
                    'coords': arrival_search['coords'],
                })
                del arrival_search['coords']
                del arrival_search['travel_time']
                arrival_search['arrival_location_id'] = arrival_search['id']
                arrival_search['departure_location_ids'] = all_locations_ids

        return data

    def processAlgorithmOutput(self, results, parameters, context, feedback):
        output_normal_fields = QgsFields()
        output_normal_fields.append(QgsField('search_id', QVariant.String, 'text', 255))
        output_normal_fields.append(QgsField('location_id', QVariant.String, 'text', 255))
        output_normal_fields.append(QgsField('travel_time', QVariant.Double, 'text', 255))
        output_normal_fields.append(QgsField('distance', QVariant.Double, 'text', 255))
        output_normal_fields.append(QgsField('departure_time', QVariant.String, 'text', 255))
        output_normal_fields.append(QgsField('arrival_time', QVariant.String, 'text', 255))

        output_detailed_fields = QgsFields()
        output_detailed_fields.append(QgsField('type', QVariant.String, 'text', 255))
        output_detailed_fields.append(QgsField('mode', QVariant.String, 'text', 255))
        output_detailed_fields.append(QgsField('directions', QVariant.String, 'text', 255))

        output_crs = EPSG4326
        output_type = QgsWkbTypes.LineString

        (sink_normal, sink_normal_id) = self.parameterAsSink(parameters, 'OUTPUT_NORMAL', context, output_normal_fields, output_type, output_crs)
        (sink_detailed, sink_detailed_id) = self.parameterAsSink(parameters, 'OUTPUT_DETAILED', context, output_detailed_fields, output_type, output_crs)

        for result in results:
            for location in result['locations']:
                feature_n = QgsFeature(output_normal_fields)

                geom_n = QgsLineString()
                for part in location['properties'][0]['route']['parts']:
                    feature_d = QgsFeature(output_detailed_fields)
                    geom_d = QgsLineString()
                    for coord in part['coords']:
                        point = QgsPoint(coord['lng'], coord['lat'])
                        geom_d.addVertex(point)
                        if geom_n.endPoint() != point:
                            geom_n.addVertex(point)

                    feature_d.setGeometry(geom_d)
                    feature_d.setAttribute(0, part['type'])
                    feature_d.setAttribute(1, part['mode'])
                    feature_d.setAttribute(2, part['directions'])
                    sink_detailed.addFeature(feature_d, QgsFeatureSink.FastInsert)

                feature_n.setGeometry(geom_n)

                feature_n.setAttribute(0, result['search_id'])
                feature_n.setAttribute(1, location['id'])
                feature_n.setAttribute(2, location['properties'][0]['travel_time'])
                feature_n.setAttribute(3, location['properties'][0]['distance'])
                feature_n.setAttribute(4, location['properties'][0]['route']['departure_time'])
                feature_n.setAttribute(5, location['properties'][0]['route']['arrival_time'])

                sink_normal.addFeature(feature_n, QgsFeatureSink.FastInsert)

        feedback.pushDebugInfo('TimeFilterAlgorithm done !')

        # to get hold of the layer in post processing
        self.sink_normal_id = sink_normal_id
        self.sink_detailed_id = sink_detailed_id

        return {
            'OUTPUT_NORMAL': sink_normal_id,
            'OUTPUT_DETAILED': sink_detailed_id,
        }

    def postProcessAlgorithm(self, context, feedback):
        style_path = os.path.join(os.path.dirname(__file__), 'resources', 'style_route_duration.qml')
        QgsProcessingUtils.mapLayerFromString(self.sink_normal_id, context).loadNamedStyle(style_path)
        style_path = os.path.join(os.path.dirname(__file__), 'resources', 'style_route_mode.qml')
        QgsProcessingUtils.mapLayerFromString(self.sink_detailed_id, context).loadNamedStyle(style_path)
        return super().postProcessAlgorithm(context, feedback)


class TimeMapSimpleAlgorithm(AlgorithmBase):
    _name = 'time_map_simple'
    _displayName = tr('Time Map - Simple')
    _group = 'Simplified'
    _groupId = 'simple'
    _icon = resources.icon_time_map_simple
    _helpUrl = 'http://docs.traveltimeplatform.com/reference/time-map/'
    _shortHelpString = tr("This algorithms provides a simpified access to the time-map endpoint.\n\nPlease see the help on {url} for more details on how to use it.").format(url=_helpUrl)

    SEARCH_TYPES = ['DEPARTURE', 'ARRIVAL']
    RESULT_TYPE = ['NORMAL', 'UNION', 'INTERSECTION']

    def initAlgorithm(self, config):

        self.addParameter(
            QgsProcessingParameterFeatureSource('INPUT_SEARCHES',
                                                tr('Searches'),
                                                [QgsProcessing.TypeVectorPoint],)
        )
        self.addParameter(
            QgsProcessingParameterEnum('INPUT_SEARCH_TYPE',
                                       tr('Search type'),
                                       options=['departure', 'arrival'])
        )
        self.addParameter(
            QgsProcessingParameterEnum('INPUT_TRNSPT_TYPE',
                                       tr('Transportation type'),
                                       options=TRANSPORTATION_TYPES)
        )
        self.addParameter(
            parameters.ParameterIsoDateTime('INPUT_TIME',
                                 tr('Departure/Arrival time (UTC)'))
        )
        self.addParameter(
            QgsProcessingParameterNumber('INPUT_TRAVEL_TIME',
                                         tr('Travel time (in minutes)'),
                                         type=0,
                                         defaultValue=15,
                                         minValue=0,
                                         maxValue=240)
        )
        self.addParameter(
            QgsProcessingParameterEnum('INPUT_RESULT_TYPE',
                                       tr('Result aggregation'),
                                       options=self.RESULT_TYPE)
        )

        # OUTPUT
        self.addParameter(
            QgsProcessingParameterFeatureSink('OUTPUT',
                                              tr('Output layer'),
                                              type=QgsProcessing.TypeVectorPolygon, )
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo('Starting TimeMapSimpleAlgorithm...')

        mode = self.SEARCH_TYPES[self.parameterAsEnum(parameters, 'INPUT_SEARCH_TYPE', context)]
        trnspt_type = TRANSPORTATION_TYPES[self.parameterAsEnum(parameters, 'INPUT_TRNSPT_TYPE', context)]
        result_type = self.RESULT_TYPE[self.parameterAsEnum(parameters, 'INPUT_RESULT_TYPE', context)]

        search_layer = self.parameterAsSource(parameters, 'INPUT_SEARCHES', context).materialize(QgsFeatureRequest())

        sub_parameters = {
            'INPUT_{}_SEARCHES'.format(mode): search_layer,
            'INPUT_{}_TRNSPT_TYPE'.format(mode): "'"+trnspt_type+"'",
            'INPUT_{}_TIME'.format(mode): "'"+self.parameterAsString(parameters, 'INPUT_TIME', context)+"'",
            'INPUT_{}_TRAVEL_TIME'.format(mode): str(self.parameterAsInt(parameters, 'INPUT_TRAVEL_TIME', context) * 60),
            'INPUT_{}_TRNSPT_WALKING_TIME'.format(mode): str(self.parameterAsInt(parameters, 'INPUT_TRAVEL_TIME', context) * 60),
            'INPUT_CALC_UNION': (result_type == 'UNION'),
            'INPUT_CALC_INTER': (result_type == 'INTERSECTION'),
            'OUTPUT_SEARCHES': 'memory:results',
            'OUTPUT_UNION': 'memory:union',
            'OUTPUT_INTER': 'memory:inter',
        }

        feedback.pushDebugInfo('Calling subcommand with following parameters...')
        feedback.pushDebugInfo(str(sub_parameters))

        results = processing.run("ttp_v4:time_map", sub_parameters, context=context, feedback=feedback)

        feedback.pushDebugInfo('Got results fom subcommand...')

        if result_type == 'UNION':
            result_layer = results['OUTPUT_UNION']
        elif result_type == 'INTERSECTION':
            result_layer = results['OUTPUT_INTER']
        else:
            result_layer = results['OUTPUT_SEARCHES']

        # Configure output
        (sink, dest_id) = self.parameterAsSink(
            parameters, 'OUTPUT', context, result_layer.fields(), result_layer.wkbType(), result_layer.sourceCrs()
        )
        # Copy results to output
        feedback.pushDebugInfo('Copying results to layer...')
        for f in result_layer.getFeatures():
            sink.addFeature(QgsFeature(f))

        feedback.pushDebugInfo('TimeMapSimpleAlgorithm done !')

        # to get hold of the layer in post processing
        self.dest_id = dest_id
        self.result_type = result_type

        return {'OUTPUT': dest_id}

    def postProcessAlgorithm(self, context, feedback):
        retval = super().postProcessAlgorithm(context, feedback)
        if self.result_type == 'UNION':
            style_file = 'style_union.qml'
        elif self.result_type == 'INTERSECTION':
            style_file = 'style_intersection.qml'
        else:
            style_file = 'style.qml'
        style_path = os.path.join(os.path.dirname(__file__), 'resources', style_file)
        QgsProcessingUtils.mapLayerFromString(self.dest_id, context).loadNamedStyle(style_path)
        return retval


class TimeFilterSimpleAlgorithm(AlgorithmBase):
    _name = 'time_filter_simple'
    _displayName = tr('Time Filter - Simple')
    _group = 'Simplified'
    _groupId = 'simple'
    _icon = resources.icon_time_filter_simple
    _helpUrl = 'http://docs.traveltimeplatform.com/reference/time-filter/'
    _shortHelpString = tr("This algorithms provides a simpified access to the time-filter endpoint.\n\nPlease see the help on {url} for more details on how to use it.").format(url=_helpUrl)

    SEARCH_TYPES = ['DEPARTURE', 'ARRIVAL']

    def initAlgorithm(self, config):

        self.addParameter(
            QgsProcessingParameterFeatureSource('INPUT_SEARCHES',
                                                tr('Searches'),
                                                [QgsProcessing.TypeVectorPoint],)
        )
        self.addParameter(
            QgsProcessingParameterEnum('INPUT_SEARCH_TYPE',
                                       tr('Search type'),
                                       options=['departure', 'arrival'])
        )
        self.addParameter(
            QgsProcessingParameterEnum('INPUT_TRNSPT_TYPE',
                                       tr('Transportation type'),
                                       options=TRANSPORTATION_TYPES)
        )
        self.addParameter(
            parameters.ParameterIsoDateTime('INPUT_TIME',
                                 tr('Departure/Arrival time (UTC)'))
        )
        self.addParameter(
            QgsProcessingParameterNumber('INPUT_TRAVEL_TIME',
                                         tr('Travel time (in minutes)'),
                                         type=0,
                                         defaultValue=15,
                                         minValue=0,
                                         maxValue=240)
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource('INPUT_LOCATIONS',
                                                tr('Locations'),
                                                [QgsProcessing.TypeVectorPoint],)
        )

        # OUTPUT
        self.addParameter(
            QgsProcessingParameterFeatureSink('OUTPUT',
                                              tr('Output layer'),
                                              type=QgsProcessing.TypeVectorPoint, )
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo('Starting TimeFilterSimpleAlgorithm...')

        mode = self.SEARCH_TYPES[self.parameterAsEnum(parameters, 'INPUT_SEARCH_TYPE', context)]
        trnspt_type = TRANSPORTATION_TYPES[self.parameterAsEnum(parameters, 'INPUT_TRNSPT_TYPE', context)]

        search_layer = self.parameterAsSource(parameters, 'INPUT_SEARCHES', context).materialize(QgsFeatureRequest())
        locations_layer = self.parameterAsSource(parameters, 'INPUT_LOCATIONS', context).materialize(QgsFeatureRequest())

        sub_parameters = {
            'INPUT_{}_SEARCHES'.format(mode): search_layer,
            'INPUT_{}_TRNSPT_TYPE'.format(mode): "'"+trnspt_type+"'",
            'INPUT_{}_TIME'.format(mode): "'"+self.parameterAsString(parameters, 'INPUT_TIME', context)+"'",
            'INPUT_{}_TRAVEL_TIME'.format(mode): str(self.parameterAsInt(parameters, 'INPUT_TRAVEL_TIME', context) * 60),
            'INPUT_{}_TRNSPT_WALKING_TIME'.format(mode): str(self.parameterAsInt(parameters, 'INPUT_TRAVEL_TIME', context) * 60),
            'INPUT_LOCATIONS'.format(mode): locations_layer,
            'OUTPUT': 'memory:results',
        }

        feedback.pushDebugInfo('Calling subcommand with following parameters...')
        feedback.pushDebugInfo(str(sub_parameters))

        results = processing.run("ttp_v4:time_filter", sub_parameters, context=context, feedback=feedback)

        feedback.pushDebugInfo('Got results fom subcommand...')

        result_layer = results['OUTPUT']

        # Configure output
        (sink, dest_id) = self.parameterAsSink(
            parameters, 'OUTPUT', context, result_layer.fields(), result_layer.wkbType(), result_layer.sourceCrs()
        )
        # Copy results to output
        feedback.pushDebugInfo('Copying results to layer...')
        for f in result_layer.getFeatures():
            sink.addFeature(QgsFeature(f))

        feedback.pushDebugInfo('TimeMapSimpleAlgorithm done !')

        # to get hold of the layer in post processing
        self.dest_id = dest_id

        return {'OUTPUT': dest_id}

    def postProcessAlgorithm(self, context, feedback):
        style_path = os.path.join(os.path.dirname(__file__), 'resources', 'style_filter.qml')
        QgsProcessingUtils.mapLayerFromString(self.sink_id, context).loadNamedStyle(style_path)
        return super().postProcessAlgorithm(context, feedback)


class RoutesSimpleAlgorithm(AlgorithmBase):
    _name = 'routes_simple'
    _displayName = tr('Routes - Simple')
    _group = 'Simplified'
    _groupId = 'simple'
    _icon = resources.icon_routes_simple
    _helpUrl = 'http://docs.traveltimeplatform.com/reference/routes/'
    _shortHelpString = tr("This algorithms provides a simpified access to the routes endpoint.\n\nPlease see the help on {url} for more details on how to use it.").format(url=_helpUrl)

    SEARCH_TYPES = ['DEPARTURE', 'ARRIVAL']
    RESULT_TYPE = ['NORMAL', 'DETAILED']

    def initAlgorithm(self, config):

        self.addParameter(
            QgsProcessingParameterFeatureSource('INPUT_SEARCHES',
                                                tr('Searches'),
                                                [QgsProcessing.TypeVectorPoint],)
        )
        self.addParameter(
            QgsProcessingParameterEnum('INPUT_SEARCH_TYPE',
                                       tr('Search type'),
                                       options=['departure', 'arrival'])
        )
        self.addParameter(
            QgsProcessingParameterEnum('INPUT_TRNSPT_TYPE',
                                       tr('Transportation type'),
                                       options=TRANSPORTATION_TYPES)
        )
        self.addParameter(
            parameters.ParameterIsoDateTime('INPUT_TIME',
                                 tr('Departure/Arrival time (UTC)'))
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource('INPUT_LOCATIONS',
                                                tr('Locations'),
                                                [QgsProcessing.TypeVectorPoint],)
        )

        # OUTPUT
        self.addParameter(
            QgsProcessingParameterEnum('INPUT_RESULT_TYPE',
                                       tr('Output style'),
                                       options=self.RESULT_TYPE)
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink('OUTPUT',
                                              tr('Output layer'),
                                              type=QgsProcessing.TypeVectorPoint, )
        )

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo('Starting RoutesSimpleAlgorithm...')

        mode = self.SEARCH_TYPES[self.parameterAsEnum(parameters, 'INPUT_SEARCH_TYPE', context)]
        trnspt_type = TRANSPORTATION_TYPES[self.parameterAsEnum(parameters, 'INPUT_TRNSPT_TYPE', context)]
        result_type = self.RESULT_TYPE[self.parameterAsEnum(parameters, 'INPUT_RESULT_TYPE', context)]

        search_layer = self.parameterAsSource(parameters, 'INPUT_SEARCHES', context).materialize(QgsFeatureRequest())
        locations_layer = self.parameterAsSource(parameters, 'INPUT_LOCATIONS', context).materialize(QgsFeatureRequest())

        sub_parameters = {
            'INPUT_{}_SEARCHES'.format(mode): search_layer,
            'INPUT_{}_TRNSPT_TYPE'.format(mode): "'"+trnspt_type+"'",
            'INPUT_{}_TIME'.format(mode): "'"+self.parameterAsString(parameters, 'INPUT_TIME', context)+"'",
            'INPUT_{}_TRNSPT_WALKING_TIME'.format(mode): str(self.parameterAsInt(parameters, 'INPUT_TRAVEL_TIME', context) * 60),
            'INPUT_LOCATIONS'.format(mode): locations_layer,
            'OUTPUT_NORMAL': 'memory:output_normal',
            'OUTPUT_DETAILED': 'memory:output_detailed',
        }

        feedback.pushDebugInfo('Calling subcommand with following parameters...')
        feedback.pushDebugInfo(str(sub_parameters))

        results = processing.run("ttp_v4:routes", sub_parameters, context=context, feedback=feedback)

        feedback.pushDebugInfo('Got results fom subcommand...')

        if result_type == 'NORMAL':
            result_layer = results['OUTPUT_NORMAL']
        else:
            result_layer = results['OUTPUT_DETAILED']

        # Configure output
        (sink, dest_id) = self.parameterAsSink(
            parameters, 'OUTPUT', context, result_layer.fields(), result_layer.wkbType(), result_layer.sourceCrs()
        )
        # Copy results to output
        feedback.pushDebugInfo('Copying results to layer...')
        for f in result_layer.getFeatures():
            sink.addFeature(QgsFeature(f))

        feedback.pushDebugInfo('TimeMapSimpleAlgorithm done !')

        # to get hold of the layer in post processing
        self.dest_id = dest_id
        self.result_type = result_type

        return {'OUTPUT': dest_id}

    def postProcessAlgorithm(self, context, feedback):
        if self.result_type == 'NORMAL':
            style_file = 'style_route_duration.qml'
        else:
            style_file = 'style_route_mode.qml'
        style_path = os.path.join(os.path.dirname(__file__), 'resources', style_file)
        QgsProcessingUtils.mapLayerFromString(self.dest_id, context).loadNamedStyle(style_path)
        return super().postProcessAlgorithm(context, feedback)

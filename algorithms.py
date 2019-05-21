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
                       QgsFields,
                       QgsField,
                       QgsFeature,
                       QgsGeometry,
                       QgsExpression,
                       QgsFeatureRequest,
                       QgsProcessingUtils)

import processing

from . import resources
from . import auth
from . import utils
from .utils import tr
from .ui import IsoDateTimeWidgetWrapper


EPSG4326 = QgsCoordinateReferenceSystem("EPSG:4326")
TRANSPORTATION_TYPES = ['cycling', 'driving', 'driving+train', 'public_transport', 'walking', 'coach', 'bus', 'train', 'ferry', 'driving+ferry', 'cycling+ferry']




class TimeMapAlgorithm(QgsProcessingAlgorithm):

    def addAdvancedParamter(self, parameter, *args, **kwargs):
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        return self.addParameter(parameter, *args, **kwargs)

    def initAlgorithm(self, config):

        # DEPARTURE and ARRIVAL parameters
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
                                                 defaultValue="'walking'",
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
        # OUTPUT
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

    def processAlgorithm(self, parameters, context, feedback):

        feedback.pushDebugInfo('Starting TimeMapAlgorithm...')

        # Get API key
        APP_ID, API_KEY = auth.get_app_id_and_api_key()
        if not APP_ID or not API_KEY:
            feedback.reportError(tr('You need a Travel Time Platform API key to make requests. Please head to {} to obtain one, and enter it in the plugin\'s setting dialog.').format('http://docs.traveltimeplatform.com/overview/getting-keys/'), fatalError=True)
            raise QgsProcessingException('App ID or api key not set')


        # Configure inputs
        source_departure = self.parameterAsSource(parameters, 'INPUT_DEPARTURE_SEARCHES', context)
        source_arrival = self.parameterAsSource(parameters, 'INPUT_ARRIVAL_SEARCHES', context)

        compute_union = self.parameterAsBool(parameters, 'INPUT_CALC_UNION', context)
        compute_inter = self.parameterAsBool(parameters, 'INPUT_CALC_INTER', context)

        # Configure expressions inputs
        expressions = {}
        expressions_contexts = {}
        for PARAM in ['INPUT_DEPARTURE_ID', 'INPUT_ARRIVAL_ID',
                      'INPUT_DEPARTURE_TRNSPT_TYPE', 'INPUT_ARRIVAL_TRNSPT_TYPE',
                      'INPUT_DEPARTURE_TRNSPT_PT_CHANGE_DELAY', 'INPUT_ARRIVAL_TRNSPT_PT_CHANGE_DELAY',
                      'INPUT_DEPARTURE_TRNSPT_WALKING_TIME', 'INPUT_ARRIVAL_TRNSPT_WALKING_TIME',
                      'INPUT_DEPARTURE_TRNSPT_DRIVING_TIME_TO_STATION', 'INPUT_ARRIVAL_TRNSPT_DRIVING_TIME_TO_STATION',
                      'INPUT_DEPARTURE_TRNSPT_PARKING_TIME', 'INPUT_ARRIVAL_TRNSPT_PARKING_TIME',
                      'INPUT_DEPARTURE_TRNSPT_BOARDING_TIME', 'INPUT_ARRIVAL_TRNSPT_BOARDING_TIME',
                      'INPUT_DEPARTURE_RANGE_WIDTH', 'INPUT_ARRIVAL_RANGE_WIDTH',
                      'INPUT_DEPARTURE_TIME', 'INPUT_ARRIVAL_TIME',
                      'INPUT_DEPARTURE_TRAVEL_TIME', 'INPUT_ARRIVAL_TRAVEL_TIME']:

            expression = QgsExpression(self.parameterAsExpression(parameters, PARAM, context))
            expression_context = self.createExpressionContext(parameters, context)
            expression.prepare(expression_context)
            expressions[PARAM] = expression
            expressions_contexts[PARAM] = expression_context

        def eval_expr(key):
            return expressions[key].evaluate(expressions_contexts[key])

        source_departure_count = source_departure.featureCount() if source_departure else 0
        source_arrival_count = source_arrival.featureCount() if source_arrival else 0

        slicing_size = 10
        slicing_count = math.ceil(max(source_departure_count, source_arrival_count) / slicing_size)

        if slicing_count > 1:
            feedback.pushInfo(tr('Input layers have more than {} features. The query will be executed in {} queries. Keep an eye on your API usage !').format(slicing_size, slicing_count))

            if compute_union or compute_inter:
                feedback.pushInfo(tr('Union or intersection will be returned per query. If you need union or interesection on the whole dataset, you will need to do so in an additional step, using QGIS vectors algorithms.'))

        results = []

        for slicing_i in range(slicing_count):
            slicing_start = slicing_i * slicing_size
            slicing_end = (slicing_i + 1) * slicing_size

            # Prepare data
            data = {}

            if compute_union:
                data['unions'] = [{'id': 'union_all', 'search_ids': []}]
            if compute_inter:
                data['intersections'] = [{'id': 'intersection_all', 'search_ids': []}]

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
                        for exp_ctx in expressions_contexts.values():
                            exp_ctx.setFeature(feature)

                        # Reproject to WGS84
                        geometry = feature.geometry()
                        geometry.transform(xform)

                        data[deparr+'_searches'].append({
                            "id": eval_expr('INPUT_'+DEPARR+'_ID'),
                            "coords": {
                                "lat": geometry.asPoint().y(),
                                "lng": geometry.asPoint().x(),
                            },
                            "transportation": {
                                "type": eval_expr('INPUT_'+DEPARR+'_TRNSPT_TYPE'),
                                "pt_change_delay": eval_expr('INPUT_'+DEPARR+'_TRNSPT_PT_CHANGE_DELAY'),
                                "walking_time": eval_expr('INPUT_'+DEPARR+'_TRNSPT_WALKING_TIME'),
                                "driving_time_to_station": eval_expr('INPUT_'+DEPARR+'_TRNSPT_DRIVING_TIME_TO_STATION'),
                                "parking_time": eval_expr('INPUT_'+DEPARR+'_TRNSPT_PARKING_TIME'),
                                "boarding_time": eval_expr('INPUT_'+DEPARR+'_TRNSPT_BOARDING_TIME'),
                            },
                            deparr+'_time': eval_expr('INPUT_'+DEPARR+'_TIME'),
                            "travel_time": eval_expr('INPUT_'+DEPARR+'_TRAVEL_TIME'),
                        })

                        # Add to aggregation if needed
                        if compute_union:
                            data['unions'][0]['search_ids'].append(eval_expr('INPUT_'+DEPARR+'_ID'))
                        if compute_inter:
                            data['intersections'][0]['search_ids'].append(eval_expr('INPUT_'+DEPARR+'_ID'))

                        # # Update the progress bar
                        # feedback.setProgress(int(current * total))

            url = 'https://api.traveltimeapp.com/v4/time-map'
            headers = {
                'Content-type': 'application/json',
                'Accept': 'application/vnd.wkt+json',
                'X-Application-Id': APP_ID,
                'X-Api-Key': API_KEY,
            }
            data = json.dumps(data)

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
                    s.setValue('travel_time_platform/current_count', count)
                    break
            else:
                feedback.reportError(tr('Execution canceled because of API limit warning.'), fatalError=True)
                raise QgsProcessingException('API usage limit warning')

            feedback.pushDebugInfo('Making request to API endpoint...')
            print_query = bool(s.value('travel_time_platform/log_calls', False))
            if print_query:
                QgsMessageLog.logMessage("Making request", 'TimeTravelPlatform')
                QgsMessageLog.logMessage("url: {}".format(url), 'TimeTravelPlatform')
                QgsMessageLog.logMessage("headers: {}".format(headers), 'TimeTravelPlatform')
                QgsMessageLog.logMessage("data: {}".format(data), 'TimeTravelPlatform')

            try:

                disable_https = QSettings().value('travel_time_platform/disable_https', False, type=bool)
                if disable_https:
                    feedback.pushInfo(tr("Warning ! HTTPS certificate verification is disabled. This means all data sent to the API can potentially be intercepted by an attacker."))

                response = requests.post(url, data=data, headers=headers, verify=not disable_https)

                feedback.pushDebugInfo('Got response from API endpoint...')
                if print_query:
                    QgsMessageLog.logMessage("Got response", 'TimeTravelPlatform')
                    QgsMessageLog.logMessage("status: {}".format(response.status_code), 'TimeTravelPlatform')
                    QgsMessageLog.logMessage("reason: {}".format(response.reason), 'TimeTravelPlatform')
                    QgsMessageLog.logMessage("text: {}".format(response.text), 'TimeTravelPlatform')

                response_data = json.loads(response.text)
                response.raise_for_status()
                results += response_data['results']

            except requests.exceptions.HTTPError as e:
                nice_info = '\n'.join('\t{}:\t{}'.format(k,v) for k,v in response_data['additional_info'].items())
                feedback.reportError(tr('Recieved error from the API.\nError code : {}\nDescription : {}\nSee : {}\nAddtionnal info :\n{}').format(response_data['error_code'],response_data['description'],response_data['documentation_link'],nice_info), fatalError=True)
                feedback.reportError(tr('See log for more details.'), fatalError=True)
                QgsMessageLog.logMessage(str(e), 'TimeTravelPlatform')
                raise QgsProcessingException('Got error {} from API'.format(response.status_code)) from None
            except requests.exceptions.SSLError as e:
                feedback.reportError(tr('Could not connect to the API because of an SSL certificate error. You can disable SSL verification in the plugin settings. See log for more details.'), fatalError=True)
                QgsMessageLog.logMessage(str(e), 'TimeTravelPlatform')
                raise QgsProcessingException('Got an SSL error when connecting to the API') from None
            except requests.exceptions.RequestException as e:
                feedback.reportError(tr('Could not connect to the API. See log for more details.'), fatalError=True)
                QgsMessageLog.logMessage(str(e), 'TimeTravelPlatform')
                raise QgsProcessingException('Could not connect to API') from None
            except ValueError as e:
                feedback.reportError(tr('Could not decode response. See log for more details.'), fatalError=True)
                QgsMessageLog.logMessage(str(e), 'TimeTravelPlatform')
                raise QgsProcessingException('Could not decode response') from None

        feedback.pushDebugInfo('Loading response to layer...')

        # Configure output
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

    def name(self):
        return 'time_map'

    def displayName(self):
        return 'Time Map'

    def group(self):
        return 'Time Map'

    def groupId(self):
        return 'time_map'

    def icon(self):
        return resources.icon

    def helpUrl(self):
        return 'http://docs.traveltimeplatform.com/reference/time-map/'

    def shortHelpString(self):
        return tr("This algorithms allows to use the time-map endpoint from the Travel Time Platform API.\n\nIt matches exactly the endpoint data structure. Please see the help on {url} for more details on how to use it.\n\nConsider using the other algorithms as they may be easier to work with.").format(url=self.helpUrl())

    def createInstance(self):
        return self.__class__()


class TimeMapSimpleAlgorithm(QgsProcessingAlgorithm):

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
            ParameterIsoDateTime('INPUT_TIME',
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

    def name(self):
        return 'time_map_simple'

    def displayName(self):
        return tr('Time Map - Simple')

    def group(self):
        return 'Time Map'

    def groupId(self):
        return 'time_map'

    def icon(self):
        return resources.icon_simplified

    def helpUrl(self):
        return 'http://docs.traveltimeplatform.com/reference/time-map/'

    def shortHelpString(self):
        return tr("This algorithms provides a simpified access to the time-map endpoint.\n\nPlease see the help on {url} for more details on how to use it.").format(url=self.helpUrl())

    def createInstance(self):
        return self.__class__()


# Custom parameter types

class ParameterIsoDateTime(QgsProcessingParameterString):

    def __init__(self, name='', description=''):
        super().__init__(name, description)
        self.setMetadata({
            'widget_wrapper': IsoDateTimeWidgetWrapper
        })

    def type(self):
        return 'ttp_datetime'

    def clone(self):
        return ParameterIsoDateTime(self.name(), self.description())

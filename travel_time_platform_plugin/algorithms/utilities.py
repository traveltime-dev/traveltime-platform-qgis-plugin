from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsPoint,
    QgsProcessing,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExpression,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterPoint,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from .. import resources
from ..libraries import iso3166
from ..utils import tr
from .base import EPSG4326, ProcessingAlgorithmBase

COUNTRIES = [(None, "-")] + list([(c.alpha2, c.name) for c in iso3166.countries])


class GeocodingAlgorithmBase(ProcessingAlgorithmBase):
    input_type = QgsProcessing.TypeVector

    RESULT_TYPE = ["ALL", "BEST_MATCH"]

    def initAlgorithm(self, config):
        super().initAlgorithm(config)

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT_DATA", tr("Input data"), [self.input_type]
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
                "OUTPUT_RESULT_TYPE",
                tr("Results type"),
                options=self.RESULT_TYPE,
                defaultValue=self.RESULT_TYPE.index("BEST_MATCH"),
            ),
            help_text="ALL will return several results per input, corresponding to all potential matches returned by the API. BEST_MATCH will only return the best point.",
        )

        # Define output parameters
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT", tr("Output"), type=QgsProcessing.TypeVectorPoint
            )
        )

    def doProcessAlgorithm(self, parameters, context, feedback):
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
            output_fields.append(QgsField("geocoded_" + attr, QVariant.String, "text"))

        (sink, sink_id) = self.parameterAsSink(
            parameters, "OUTPUT", context, output_fields, QgsWkbTypes.Point, EPSG4326
        )

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
                    response_geojson["features"],
                    key=lambda f: -f["properties"]["score"],
                )[0:1]

            # If there were no results, we add an empty row to create a feature
            if len(results) == 0:
                results.append(None)

            for result in results:
                newfeature = QgsFeature(output_fields)

                # Clone the existing attributes
                for i in range(len(source_data.fields())):
                    newfeature.setAttribute(i, feature.attribute(i))

                if result is not None:
                    # Add our attributes
                    props = result["properties"]
                    for attr in response_attributes:
                        output_fields.append(QgsField(attr, QVariant.String, "text"))
                        newfeature.setAttribute(
                            "geocoded_" + attr, props[attr] if attr in props else None
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
    input_type = QgsProcessing.TypeVector
    url = "/v4/geocoding/search"
    method = "GET"

    _name = "geocoding"
    _displayName = tr("Geocoding")
    _group = "Utilities"
    _groupId = "utils"
    _icon = resources.icon_geocoding
    _helpUrl = "https://docs.traveltime.com/api/reference/geocoding-search/"
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
        params = {"query": self.eval_expr("INPUT_QUERY_FIELD")}
        if self.params["INPUT_FOCUS"]:
            params.update(
                {
                    "focus.lat": self.params["INPUT_FOCUS"].y(),
                    "focus.lng": self.params["INPUT_FOCUS"].x(),
                }
            )
        return params


class ReverseGeocodingAlgorithm(GeocodingAlgorithmBase):
    input_type = QgsProcessing.TypeVectorPoint
    url = "/v4/geocoding/reverse"
    method = "GET"

    _name = "reverse_geocoding"
    _displayName = tr("Reverse Geocoding")
    _group = "Utilities"
    _groupId = "utils"
    _icon = resources.icon_reverse_geocoding
    _helpUrl = "https://docs.traveltime.com/api/reference/geocoding-reverse/"
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

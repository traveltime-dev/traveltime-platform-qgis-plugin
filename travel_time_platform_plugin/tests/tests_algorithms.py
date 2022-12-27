import processing
from qgis.core import QgsFeature, QgsProject

from ..algorithms.utilities import GeocodingAlgorithmBase
from .base import TestCaseBase


class AlgorithmsBasicTest(TestCaseBase):
    """Testing algorithms with basic parameters (mostly default)"""

    def test_processing_time_map_simple(self):
        input_lyr = self._make_layer(["POINT(-3.1 55.9)"])
        results = processing.runAndLoadResults(
            "ttp_v4:time_map_simple",
            {
                "INPUT_SEARCHES": input_lyr,
                "INPUT_TIME": self._today_at_noon().isoformat(),
                "OUTPUT": "memory:",
                # TODO: these inputs should work without values
                "INPUT_SEARCH_TYPE": 0,
                "INPUT_TRNSPT_TYPE": 0,
                "OUTPUT_RESULT_TYPE": 0,
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 1)

    def test_processing_time_filter_simple(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"])
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"]
        )
        results = processing.runAndLoadResults(
            "ttp_v4:time_filter_simple",
            {
                "INPUT_SEARCHES": input_lyr_a,
                "INPUT_LOCATIONS": input_lyr_b,
                "INPUT_TIME": self._today_at_noon().isoformat(),
                "INPUT_TRAVEL_TIME": 15,
                "OUTPUT": "memory:",
                # TODO: these inputs should work without values
                "INPUT_SEARCH_TYPE": 0,
                "INPUT_TRNSPT_TYPE": 0,
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 3)

    def test_processing_routes_simple(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"])
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"]
        )
        results = processing.runAndLoadResults(
            "ttp_v4:routes_simple",
            {
                "INPUT_SEARCHES": input_lyr_a,
                "INPUT_LOCATIONS": input_lyr_b,
                "INPUT_TIME": self._today_at_noon().isoformat(),
                "OUTPUT": "memory:",
                # TODO: these inputs should work without values
                "INPUT_SEARCH_TYPE": 0,
                "INPUT_TRNSPT_TYPE": 0,
                "OUTPUT_RESULT_TYPE": 0,
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 3)

    def test_processing_time_map(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"])
        results = processing.runAndLoadResults(
            "ttp_v4:time_map",
            {
                "INPUT_DEPARTURE_SEARCHES": input_lyr_a,
                "INPUT_DEPARTURE_TIME": self._today_at_noon().isoformat(),
                "INPUT_DEPARTURE_TRAVEL_TIME": "900",
                "INPUT_THROTTLING_STRATEGY": 0,
                "OUTPUT": "memory:",
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 1)

    def test_processing_time_filter(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"])
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(0.2 51.5)", "POINT(0.3 51.5)"]
        )
        results = processing.runAndLoadResults(
            "ttp_v4:time_filter",
            {
                "INPUT_DEPARTURE_SEARCHES": input_lyr_a,
                "INPUT_DEPARTURE_TIME": self._today_at_noon().isoformat(),
                "INPUT_DEPARTURE_TRAVEL_TIME": "900",
                "INPUT_LOCATIONS": input_lyr_b,
                "INPUT_THROTTLING_STRATEGY": 0,
                "OUTPUT": "memory:",
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 3)

    def test_processing_routes(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"])
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"]
        )
        results = processing.runAndLoadResults(
            "ttp_v4:routes",
            {
                "INPUT_DEPARTURE_SEARCHES": input_lyr_a,
                "INPUT_DEPARTURE_TIME": self._today_at_noon().isoformat(),
                "INPUT_DEPARTURE_TRAVEL_TIME": "900",
                "INPUT_LOCATIONS": input_lyr_b,
                "INPUT_THROTTLING_STRATEGY": 0,
                "OUTPUT": "memory:",
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 3)

    def test_processing_geocoding(self):
        input_lyr = self._make_layer(
            [],
            layer_type="NoGeometry?crs=EPSG:4326&field=place:string(255,0)",
        )
        for place in ["London", "Birmingham Palace", "Newcastle"]:
            feat = QgsFeature()
            feat.setFields(input_lyr.fields())
            feat.setAttribute("place", place)
            input_lyr.dataProvider().addFeature(feat)

        results = processing.runAndLoadResults(
            "ttp_v4:geocoding",
            {
                "INPUT_DATA": input_lyr,
                "INPUT_THROTTLING_STRATEGY": 0,
                "INPUT_QUERY_FIELD": '"place"',
                "OUTPUT": "memory:",
                "OUTPUT_RESULT_TYPE": GeocodingAlgorithmBase.RESULT_TYPE.index(
                    "BEST_MATCH"
                ),
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 3)

    def test_processing_reverse_geocoding(self):
        input_lyr = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"]
        )
        results = processing.runAndLoadResults(
            "ttp_v4:reverse_geocoding",
            {
                "INPUT_DATA": input_lyr,
                "INPUT_THROTTLING_STRATEGY": 0,
                "OUTPUT": "memory:",
                "OUTPUT_RESULT_TYPE": GeocodingAlgorithmBase.RESULT_TYPE.index(
                    "BEST_MATCH"
                ),
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 3)

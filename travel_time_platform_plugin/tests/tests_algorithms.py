import itertools
import random

import processing
from qgis.core import QgsFeature, QgsProject

from ..algorithms.simple import TRANSPORTATION_TYPES, TimeMapSimpleAlgorithm
from ..utils import timezones
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
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 1)

    def test_processing_time_filter_simple(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"], name="a")
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"], name="b"
        )
        results = processing.runAndLoadResults(
            "ttp_v4:time_filter_simple",
            {
                "INPUT_SEARCHES": input_lyr_a,
                "INPUT_LOCATIONS": input_lyr_b,
                "INPUT_TIME": self._today_at_noon().isoformat(),
                "INPUT_TRAVEL_TIME": 15,
                "OUTPUT": "memory:",
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 3)

    def test_processing_routes_simple(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"], name="a")
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"], name="b"
        )
        results = processing.runAndLoadResults(
            "ttp_v4:routes_simple",
            {
                "INPUT_SEARCHES": input_lyr_a,
                "INPUT_LOCATIONS": input_lyr_b,
                "INPUT_TIME": self._today_at_noon().isoformat(),
                "OUTPUT": "memory:",
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
                "OUTPUT": "memory:",
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 1)

    def test_processing_time_filter(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"], name="a")
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(0.2 51.5)", "POINT(0.3 51.5)"], name="b"
        )
        results = processing.runAndLoadResults(
            "ttp_v4:time_filter",
            {
                "INPUT_DEPARTURE_SEARCHES": input_lyr_a,
                "INPUT_DEPARTURE_TIME": self._today_at_noon().isoformat(),
                "INPUT_DEPARTURE_TRAVEL_TIME": "900",
                "INPUT_LOCATIONS": input_lyr_b,
                "OUTPUT": "memory:",
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 3)

    def test_processing_routes(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"], name="a")
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"], name="b"
        )
        results = processing.runAndLoadResults(
            "ttp_v4:routes",
            {
                "INPUT_DEPARTURE_SEARCHES": input_lyr_a,
                "INPUT_DEPARTURE_TIME": self._today_at_noon().isoformat(),
                "INPUT_DEPARTURE_TRAVEL_TIME": "900",
                "INPUT_LOCATIONS": input_lyr_b,
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
                "INPUT_QUERY_FIELD": '"place"',
                "OUTPUT": "memory:",
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
                "OUTPUT": "memory:",
            },
        )
        output_layer = QgsProject.instance().mapLayer(results["OUTPUT"])
        self.assertEqual(output_layer.featureCount(), 3)


class AlgorithmsFeaturesTest(TestCaseBase):
    def test_processing_time_map_level_of_detail(self):
        """Test combinations of level_of_detail, no_holes, and single_shapes. This makes sure that
        both the simple and advanced algorithm return the same results"""

        self._center(-0.018, 51.504, 50000)
        input_lyr = self._make_layer(["POINT(-0.018 51.504)"])

        now = self._today_at_noon().isoformat()
        params_simple = {
            "INPUT_SEARCHES": input_lyr,
            "INPUT_TIME": now,
            "INPUT_TRNSPT_TYPE": TRANSPORTATION_TYPES.index("driving"),
            "INPUT_TRAVEL_TIME": 15,
            "SETTINGS_TIMEZONE": timezones.index("UTC"),
            "OUTPUT": "memory:",
        }
        params_advanced = {
            "INPUT_DEPARTURE_SEARCHES": input_lyr,
            "INPUT_DEPARTURE_TIME": f"'{now}'",
            "INPUT_DEPARTURE_TRNSPT_TYPE": "'driving'",
            "INPUT_DEPARTURE_TRAVEL_TIME": 15 * 60,
            "OUTPUT": "memory:",
        }

        # lods = [None, "lowest", "low", "medium", "high","highest"] # not possible with this API key
        lods = [None, "lowest", "low", "medium"]
        no_holes = [None, False, True]
        single_shapes = [None, False, True]
        combinations = list(itertools.product(lods, no_holes, single_shapes))

        # we only test a deterministic subset of the combinations
        random.Random(0).shuffle(combinations)
        combinations = combinations[0:10]

        for lod, no_hole, single_shape in combinations:
            # Run the simple
            results_simple = processing.runAndLoadResults(
                "ttp_v4:time_map_simple",
                {
                    **params_simple,
                    "INPUT_LEVEL_OF_DETAIL": (
                        None
                        if lod is None
                        else TimeMapSimpleAlgorithm.LEVELS_OF_DETAILS.index(lod)
                    ),
                    "INPUT_NO_HOLES": no_hole,
                    "INPUT_SINGLE_SHAPE": single_shape,
                },
            )
            output_layer_simple = QgsProject.instance().mapLayer(
                results_simple["OUTPUT"]
            )
            output_layer_simple.setName(
                f"simple lod: {lod}  no-holes: {no_hole}  single: {single_shape}"
            )

            # Run the advanced
            results_advanced = processing.runAndLoadResults(
                "ttp_v4:time_map",
                {
                    **params_advanced,
                    "INPUT_DEPARTURE_LEVEL_OF_DETAIL": None
                    if lod is None
                    else f"'{lod}'",
                    "INPUT_DEPARTURE_NO_HOLES": str(no_hole),
                    "INPUT_DEPARTURE_SINGLE_SHAPE": str(single_shape),
                },
            )
            output_layer_advanced = QgsProject.instance().mapLayer(
                results_advanced["OUTPUT"]
            )
            output_layer_advanced.setName(
                f"advanced lod: {lod}  no-holes: {no_hole}  single: {single_shape}"
            )

            # If all params are set, both results should be the same
            # (otherwise, default values may differ)
            if lod is not None and no_hole is not None and single_shape is not None:
                self.assertEqual(
                    output_layer_simple.getFeature(1),
                    output_layer_advanced.getFeature(1),
                )

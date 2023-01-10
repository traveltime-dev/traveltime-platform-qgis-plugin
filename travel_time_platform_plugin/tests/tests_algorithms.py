import itertools
import json

import processing
from qgis.core import QgsFeature, QgsProcessingUtils, QgsProject

from ..algorithms.simple import TRANSPORTATION_TYPES, TimeMapSimpleAlgorithm
from ..constants import TTP_VERSION
from ..utils import timezones
from .base import TestCaseBase


class AlgorithmsBasicTest(TestCaseBase):
    """Testing algorithms with basic parameters (mostly default)"""

    def _test_algorithm(self, algorithm_name, parameters, expected_result_count):
        """Runs tests on the given algorithm"""

        # Run the algorithm
        context = processing.createContext()
        results = processing.runAndLoadResults(
            algorithm_name,
            {**parameters},  # copy the dict, as runAndLoadResults alters it (sic !)
            context=context,
        )

        # Get the output layer
        output_layer = QgsProcessingUtils.mapLayerFromString(results["OUTPUT"], context)

        # self._feedback(20)

        # Ensure we got the expected number of features
        self.assertEqual(
            output_layer.featureCount(),
            expected_result_count,
        )

        # Assert TTP_ALGORITHM metadata
        self.assertEquals(
            output_layer.metadata().keywords("TTP_ALGORITHM")[0],
            algorithm_name,
        )

        # Assert TTP_PARAMS metadata
        self.assertEquals(
            json.loads(output_layer.metadata().keywords("TTP_PARAMS")[0]),
            parameters,
            f"{output_layer.metadata().keywords('TTP_PARAMS')[0]}\n\n\nIS DIFFERNT FROM\n\n\n{parameters}",
        )

        # Assert TTP_VERSION metadata
        self.assertEquals(
            output_layer.metadata().keywords("TTP_VERSION")[0],
            TTP_VERSION,
        )

    def test_processing_time_map_simple(self):
        input_lyr = self._make_layer(["POINT(-3.1 55.9)"])
        self._test_algorithm(
            "ttp_v4:time_map_simple",
            {
                "INPUT_SEARCHES": input_lyr.id(),
                "INPUT_TIME": self._today_at_noon().isoformat(),
                "OUTPUT": "memory:",
            },
            expected_result_count=1,
        )

    def test_processing_time_filter_simple(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"], name="a")
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"], name="b"
        )
        self._test_algorithm(
            "ttp_v4:time_filter_simple",
            {
                "INPUT_SEARCHES": input_lyr_a.id(),
                "INPUT_LOCATIONS": input_lyr_b.id(),
                "INPUT_TIME": self._today_at_noon().isoformat(),
                "INPUT_TRAVEL_TIME": 15,
                "OUTPUT": "memory:",
            },
            expected_result_count=3,
        )

    def test_processing_routes_simple(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"], name="a")
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"], name="b"
        )
        self._test_algorithm(
            "ttp_v4:routes_simple",
            {
                "INPUT_SEARCHES": input_lyr_a.id(),
                "INPUT_LOCATIONS": input_lyr_b.id(),
                "INPUT_TIME": self._today_at_noon().isoformat(),
                "OUTPUT": "memory:",
            },
            expected_result_count=3,
        )

    def test_processing_time_map(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"])
        self._test_algorithm(
            "ttp_v4:time_map",
            {
                "INPUT_DEPARTURE_SEARCHES": input_lyr_a.id(),
                "INPUT_DEPARTURE_TIME": self._today_at_noon().isoformat(),
                "INPUT_DEPARTURE_TRAVEL_TIME": "900",
                "OUTPUT": "memory:",
            },
            expected_result_count=1,
        )

    def test_processing_time_filter(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"], name="a")
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(0.2 51.5)", "POINT(0.3 51.5)"], name="b"
        )
        self._test_algorithm(
            "ttp_v4:time_filter",
            {
                "INPUT_DEPARTURE_SEARCHES": input_lyr_a.id(),
                "INPUT_DEPARTURE_TIME": self._today_at_noon().isoformat(),
                "INPUT_DEPARTURE_TRAVEL_TIME": "900",
                "INPUT_LOCATIONS": input_lyr_b.id(),
                "OUTPUT": "memory:",
            },
            expected_result_count=3,
        )

    def test_processing_routes(self):
        input_lyr_a = self._make_layer(["POINT(0.0 51.5)"], name="a")
        input_lyr_b = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"], name="b"
        )
        self._test_algorithm(
            "ttp_v4:routes",
            {
                "INPUT_DEPARTURE_SEARCHES": input_lyr_a.id(),
                "INPUT_DEPARTURE_TIME": self._today_at_noon().isoformat(),
                "INPUT_DEPARTURE_TRAVEL_TIME": "900",
                "INPUT_LOCATIONS": input_lyr_b.id(),
                "OUTPUT": "memory:",
            },
            expected_result_count=3,
        )

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

        self._test_algorithm(
            "ttp_v4:geocoding",
            {
                "INPUT_DATA": input_lyr.id(),
                "INPUT_QUERY_FIELD": '"place"',
                "OUTPUT": "memory:",
            },
            expected_result_count=3,
        )

    def test_processing_reverse_geocoding(self):
        input_lyr = self._make_layer(
            ["POINT(0.1 51.5)", "POINT(-0.1 51.5)", "POINT(0.0 51.6)"]
        )
        self._test_algorithm(
            "ttp_v4:reverse_geocoding",
            {
                "INPUT_DATA": input_lyr.id(),
                "OUTPUT": "memory:",
            },
            expected_result_count=3,
        )


class AlgorithmsFeaturesTest(TestCaseBase):
    def test_processing_time_map_level_of_detail(self):
        """Test combinations of level_of_detail, no_holes, and single_shapes. This makes sure that
        both the simple and advanced algorithm return the same results"""

        self._center(-0.018, 51.504, 50000)
        input_lyr = self._make_layer(["POINT(-0.018 51.504)"])

        now = self._today_at_noon().isoformat()
        params_simple = {
            "INPUT_SEARCHES": input_lyr,
            "INPUT_ID": "'search_id_' || $id",
            "INPUT_TIME": now,
            "INPUT_TRNSPT_TYPE": TRANSPORTATION_TYPES.index("driving"),
            "INPUT_TRAVEL_TIME": 15,
            "SETTINGS_TIMEZONE": timezones.index("UTC"),
            "OUTPUT": "memory:",
        }
        params_advanced = {
            "INPUT_DEPARTURE_SEARCHES": input_lyr,
            "INPUT_DEPARTURE_ID": "'search_id_' || $id",
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

        # Uncomment this to only test a subset of the combinations
        # random.Random(0).shuffle(combinations)
        # combinations = combinations[0:10]

        for lod, no_hole, single_shape in combinations:

            subcase_name = f"{lod=} / {no_hole=} / {single_shape=}"

            params_s = {**params_simple}
            params_a = {**params_advanced}

            if lod is not None:
                lod_idx = TimeMapSimpleAlgorithm.LEVELS_OF_DETAILS.index(lod)
                params_s.update({"INPUT_LEVEL_OF_DETAIL": lod_idx})
                params_a.update({"INPUT_DEPARTURE_LEVEL_OF_DETAIL": f"'{lod}'"})

            if no_hole is True:
                params_s.update({"INPUT_NO_HOLES": True})
                params_a.update({"INPUT_DEPARTURE_NO_HOLES": "true"})
            elif no_hole is False:
                params_s.update({"INPUT_NO_HOLES": False})
                params_a.update({"INPUT_DEPARTURE_NO_HOLES": "false"})
            else:
                # default forced by simple tool
                params_a.update({"INPUT_DEPARTURE_NO_HOLES": "false"})

            if single_shape is True:
                params_s.update({"INPUT_SINGLE_SHAPE": True})
                params_a.update({"INPUT_DEPARTURE_SINGLE_SHAPE": "true"})
            elif single_shape is False:
                params_s.update({"INPUT_SINGLE_SHAPE": False})
                params_a.update({"INPUT_DEPARTURE_SINGLE_SHAPE": "false"})
            else:
                # default forced by simple tool
                params_a.update({"INPUT_DEPARTURE_SINGLE_SHAPE": "false"})

            # Run the simple
            results_s = processing.runAndLoadResults("ttp_v4:time_map_simple", params_s)
            output_s = QgsProject.instance().mapLayer(results_s["OUTPUT"])
            output_s.setName(f"simple {subcase_name}")

            # Run the advanced
            results_a = processing.runAndLoadResults("ttp_v4:time_map", params_a)
            output_a = QgsProject.instance().mapLayer(results_a["OUTPUT"])
            output_a.setName(f"advanced {subcase_name}")

            # Both results should be the same
            ft_simple = output_s.getFeature(1)
            ft_advanced = output_a.getFeature(1)
            self.assertEqual(
                ft_simple,
                ft_advanced,
                f"Simple and advanced algorithm did not yield same results for {subcase_name}",
            )

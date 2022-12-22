from datetime import datetime
from itertools import product

from qgis.core import QgsPointXY, QgsProject
from qgis.utils import iface

from .base import TestCaseBase


class ExpressToolsTest(TestCaseBase):
    def test_express_time_map_action(self):

        # Use the action
        self.plugin.express_time_map_action.trigger()
        self._feedback()
        self._click(QgsPointXY(-0.13, 51.5))

        # Ensure we got exactly one output
        output_layers = QgsProject.instance().mapLayersByName("Output")
        self.assertEqual(len(output_layers), 1)

        # Ensure the output got exactly one feature
        output_layer = output_layers[0]
        self.assertEqual(output_layer.featureCount(), 1)

    def test_express_time_filter_action(self):

        # Create a data layer
        vl = self._make_layer(
            [
                f"POINT({-0.13+x/100} {51.50+y/100})"
                for x, y in product(range(-5, 5), range(-5, 5))
            ]
        )
        iface.setActiveLayer(vl)

        # Use the action
        self.plugin.express_time_filter_action.trigger()
        self._click(QgsPointXY(-0.13, 51.5))

        # Ensure we got exactly one output
        output_layers = QgsProject.instance().mapLayersByName("Output")
        self.assertEqual(len(output_layers), 1)

        # Ensure the output got some features
        output_layer = output_layers[0]
        self.assertGreater(output_layer.featureCount(), 0)

    def test_express_route_action(self):

        # Configure the time
        self.plugin.express_route_action.menu.show()
        self._feedback()
        self.plugin.express_route_action.widget.dateTimeEdit.setDateTime(
            datetime.now().replace(hour=12, minute=30, second=0)
        )
        self._feedback()
        self.plugin.express_route_action.menu.hide()

        # Use the action
        self.plugin.express_route_action.trigger()
        self._feedback()
        self._click(QgsPointXY(-0.1253, 51.5084))
        self._click(QgsPointXY(-0.1238, 51.5306))

        # Ensure we got exactly one output
        output_layers = QgsProject.instance().mapLayersByName("Output")
        self.assertEqual(len(output_layers), 1)

        # Ensure the output got some features
        output_layer = output_layers[0]
        self.assertGreater(output_layer.featureCount(), 0)

    def test_geoclick(self):

        # Configure the time
        self.plugin.express_geoclick_lineedit.setText("London")
        self.plugin.express_geoclick_action.trigger()
        self._feedback()
        self.assertLess(
            QgsPointXY(-0.1276, 51.5072).distance(iface.mapCanvas().center()), 0.1
        )

        self.plugin.express_geoclick_lineedit.setText("Edinburgh")
        self.plugin.express_geoclick_action.trigger()
        self._feedback()
        self.assertLess(
            QgsPointXY(-3.1883, 55.9533).distance(iface.mapCanvas().center()), 0.1
        )

        self.plugin.express_geoclick_lineedit.setText("Glasgow")
        self.plugin.express_geoclick_action.trigger()
        self._feedback()
        self.assertLess(
            QgsPointXY(-4.2518, 55.8642).distance(iface.mapCanvas().center()), 0.1
        )

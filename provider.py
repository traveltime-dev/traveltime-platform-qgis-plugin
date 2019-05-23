from qgis.core import QgsProcessingProvider

from . import algorithms
from .utils import tr
from . import resources


class Provider(QgsProcessingProvider):
    def unload(self):
        pass

    def loadAlgorithms(self):
        self.addAlgorithm(algorithms.simple.TimeMapSimpleAlgorithm())
        self.addAlgorithm(algorithms.simple.TimeFilterSimpleAlgorithm())
        self.addAlgorithm(algorithms.simple.RoutesSimpleAlgorithm())
        self.addAlgorithm(algorithms.advanced.TimeMapAlgorithm())
        self.addAlgorithm(algorithms.advanced.TimeFilterAlgorithm())
        self.addAlgorithm(algorithms.advanced.RoutesAlgorithm())
        self.addAlgorithm(algorithms.utilities.GeocodingAlgorithm())
        self.addAlgorithm(algorithms.utilities.ReverseGeocodingAlgorithm())

    def id(self):
        return "ttp_v4"

    def name(self):
        return "Travel Time Platform"

    def longName(self):
        return self.name()

    def icon(self):
        return resources.icon_general

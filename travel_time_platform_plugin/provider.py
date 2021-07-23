from qgis.core import QgsProcessingProvider

from . import algorithms, resources


class Provider(QgsProcessingProvider):
    def unload(self):
        pass

    def loadAlgorithms(self):
        self.addAlgorithm(algorithms.simple.TimeMapSimpleAlgorithm())
        self.addAlgorithm(algorithms.simple.TimeFilterSimpleAlgorithm())
        self.addAlgorithm(algorithms.simple.RoutesSimpleAlgorithm())
        self.addAlgorithm(algorithms.advanced.TimeMapAlgorithmDeparture())
        self.addAlgorithm(algorithms.advanced.TimeFilterAlgorithmDeparture())
        self.addAlgorithm(algorithms.advanced.RoutesAlgorithmDeparture())
        self.addAlgorithm(algorithms.advanced.TimeMapAlgorithmArrival())
        self.addAlgorithm(algorithms.advanced.TimeFilterAlgorithmArrival())
        self.addAlgorithm(algorithms.advanced.RoutesAlgorithmArrival())
        self.addAlgorithm(algorithms.advanced.TimeMapAlgorithm())
        self.addAlgorithm(algorithms.advanced.TimeFilterAlgorithm())
        self.addAlgorithm(algorithms.advanced.RoutesAlgorithm())
        self.addAlgorithm(algorithms.utilities.GeocodingAlgorithm())
        self.addAlgorithm(algorithms.utilities.ReverseGeocodingAlgorithm())

    def id(self):
        return "ttp_v4"

    def name(self):
        return "TravelTime platform"

    def longName(self):
        return self.name()

    def icon(self):
        return resources.icon_general

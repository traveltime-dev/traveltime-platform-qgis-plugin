from qgis.core import QgsProcessingProvider

from . import algorithms
from .utils import tr
from . import resources


class Provider(QgsProcessingProvider):

    def unload(self):
        pass

    def loadAlgorithms(self):
        self.addAlgorithm(algorithms.TimeMapSimpleAlgorithm())
        self.addAlgorithm(algorithms.TimeFilterSimpleAlgorithm())
        self.addAlgorithm(algorithms.TimeMapAlgorithm())
        self.addAlgorithm(algorithms.TimeFilterAlgorithm())

    def id(self):
        return 'ttp_v4'

    def name(self):
        return 'Travel Time Platform'

    def longName(self):
        return self.name()

    def icon(self):
        return resources.icon


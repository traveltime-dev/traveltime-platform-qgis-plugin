from qgis.core import QgsProcessingProvider

from .algorithms import TimeMapAlgorithm, TimeMapSimpleAlgorithm
from .utils import tr
from . import resources


class Provider(QgsProcessingProvider):

    def unload(self):
        pass

    def loadAlgorithms(self):
        self.addAlgorithm(TimeMapSimpleAlgorithm())
        self.addAlgorithm(TimeMapAlgorithm())

    def id(self):
        return 'ttp_v4'

    def name(self):
        return 'Travel Time Platform'

    def longName(self):
        return self.name()

    def icon(self):
        return resources.icon


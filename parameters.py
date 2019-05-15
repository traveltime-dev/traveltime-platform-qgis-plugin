from qgis.core import QgsProcessingParameterString
from .ui import IsoDateTimeWidgetWrapper

# Custom parameter types


class ParameterIsoDateTime(QgsProcessingParameterString):
    def __init__(self, name="", description=""):
        super().__init__(name, description)
        self.setMetadata({"widget_wrapper": IsoDateTimeWidgetWrapper})

    def type(self):
        return "ttp_datetime"

    def clone(self):
        return ParameterIsoDateTime(self.name(), self.description())

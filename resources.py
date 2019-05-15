import os

from qgis.PyQt.QtGui import QIcon

logo = QIcon(os.path.join(os.path.dirname(__file__), "resources", "ttp_logo.svg"))

icon_tiles = QIcon(
    os.path.join(
        os.path.dirname(__file__), "resources", "icons/icon_background_tiles_16x16.svg"
    )
)
icon_config = QIcon(
    os.path.join(
        os.path.dirname(__file__), "resources", "icons/icon_configuration_16x16.svg"
    )
)
icon_general = QIcon(
    os.path.join(os.path.dirname(__file__), "resources", "icons/icon_general_16x16.svg")
)
icon_geocoding = QIcon(
    os.path.join(
        os.path.dirname(__file__), "resources", "icons/icon_geocoding_32x32.svg"
    )
)
icon_help = QIcon(
    os.path.join(os.path.dirname(__file__), "resources", "icons/icon_help_16x16.svg")
)
icon_routes_advanced = QIcon(
    os.path.join(os.path.dirname(__file__), "resources", "icons/icon_routes_16x16.svg")
)
icon_routes_simple = QIcon(
    os.path.join(os.path.dirname(__file__), "resources", "icons/icon_routes_16x16.svg")
)
icon_time_filter_advanced = QIcon(
    os.path.join(
        os.path.dirname(__file__),
        "resources",
        "icons/icon_time_filter_advanced_16x16.svg",
    )
)
icon_time_filter_simple = QIcon(
    os.path.join(
        os.path.dirname(__file__),
        "resources",
        "icons/icon_time_filter_simple_16x16.svg",
    )
)
icon_time_map_advanced = QIcon(
    os.path.join(
        os.path.dirname(__file__), "resources", "icons/icon_time_map_advanced_16x16.svg"
    )
)
icon_time_map_simple = QIcon(
    os.path.join(
        os.path.dirname(__file__), "resources", "icons/icon_time_map_simple_16x16.svg"
    )
)

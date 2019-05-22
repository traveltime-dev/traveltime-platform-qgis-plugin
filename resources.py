import os

from qgis.PyQt.QtGui import QIcon


def icon(icon_name):
    return QIcon(os.path.join(os.path.dirname(__file__), "resources", icon_name))


logo = icon("ttp_logo.svg")

icon_tiles = icon("icons/icon_background_tiles_16x16.svg")
icon_config = icon("icons/icon_configuration_16x16.svg")
icon_general = icon("icons/icon_general_16x16.svg")
icon_geocoding = icon("icons/icon_geocoding_32x32.svg")
icon_reverse_geocoding = icon("icons/icon_reverse_geocoding_32x32.svg")
icon_help = icon("icons/icon_help_16x16.svg")
icon_routes_advanced = icon("icons/icon_routes_16x16.svg")
icon_routes_simple = icon("icons/icon_routes_16x16.svg")
icon_time_filter_advanced = icon("icons/icon_time_filter_advanced_16x16.svg")
icon_time_filter_simple = icon("icons/icon_time_filter_simple_16x16.svg")
icon_time_map_advanced = icon("icons/icon_time_map_advanced_16x16.svg")
icon_time_map_simple = icon("icons/icon_time_map_simple_16x16.svg")

tiles_preview_darkmatter = icon("tiles_previews/dark-matter.png")
tiles_preview_klokantech = icon("tiles_previews/klokantech-basic.png")
tiles_preview_osm = icon("tiles_previews/osm-bright.png")
tiles_preview_positron = icon("tiles_previews/positron.png")

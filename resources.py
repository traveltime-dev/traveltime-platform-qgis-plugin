import os

from qgis.PyQt.QtGui import QIcon


def icon(icon_name):
    return QIcon(os.path.join(os.path.dirname(__file__), "resources", icon_name))


logo = icon("ttp_logo.svg")

icon_toolbox = icon("icons/toolbox.svg")
icon_tiles = icon("icons/tiles.svg")
icon_config = icon("icons/settings.svg")
icon_general = icon("icons/general.svg")
icon_geocoding = icon("icons/geocoding.svg")
icon_reverse_geocoding = icon("icons/geocoding_reversed.svg")
icon_help = icon("icons/help.svg")
icon_routes_advanced = icon("icons/route_advanced.svg")
icon_routes_simple = icon("icons/route_simple.svg")
icon_routes_express = icon("icons/route_express.svg")
icon_time_filter_advanced = icon("icons/timefilter_advanced.svg")
icon_time_filter_simple = icon("icons/timefilter_simple.svg")
icon_time_filter_express = icon("icons/timefilter_express.svg")
icon_time_map_advanced = icon("icons/timemap_advanced.svg")
icon_time_map_simple = icon("icons/timemap_simple.svg")
icon_time_map_express = icon("icons/timemap_express.svg")

tiles_preview_darkmatter = icon("tiles_previews/dark-matter.png")
tiles_preview_klokantech = icon("tiles_previews/klokantech-basic.png")
tiles_preview_osm = icon("tiles_previews/osm-bright.png")
tiles_preview_positron = icon("tiles_previews/positron.png")

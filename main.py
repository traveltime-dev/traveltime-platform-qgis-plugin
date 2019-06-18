import os.path
import requests
import functools

from qgis.PyQt.QtCore import (
    Qt,
    QSettings,
    QCoreApplication,
    QTranslator,
    QSize,
    QItemSelectionModel,
)
from qgis.PyQt.QtWidgets import (
    QAction,
    QLabel,
    QDockWidget,
    QMessageBox,
    QInputDialog,
    QLineEdit,
    QPushButton,
    QToolButton,
    QMenu,
    QDockWidget,
    QWidget,
    QSplitter,
    QTreeView,
)
from qgis.core import Qgis, QgsApplication
from qgis.gui import QgsFilterLineEdit

from .provider import Provider
from .utils import tr, log
from . import resources
from . import auth
from . import ui
from . import express
from . import auth
from . import tiles


class Main:
    def __init__(self, iface):
        self.iface = iface

        self.plugin_dir = os.path.dirname(__file__)

        locale = QSettings().value("locale/userLocale")[0:2]
        locale_path = os.path.join(
            self.plugin_dir, "i18n", "traveltime_platform_{}.qm".format(locale)
        )

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.provider = Provider()

    def initGui(self):
        # Add GUI elements
        self.splash_screen = ui.SplashScreen(self)
        self.config_dialog = ui.ConfigDialog()
        self.help_dialog = ui.HelpWidget(self)
        self.tilesManager = tiles.TilesManager(self)

        self.toolbar = self.iface.addToolBar("TravelTime platform Toolbar")

        # Logo
        button = QPushButton(resources.logo, "")
        button.setIconSize(QSize(112, 30))
        button.setFlat(True)
        button.pressed.connect(self.show_splash)
        self.toolbar.addWidget(button)

        self.toolbar.addSeparator()

        # Show toolbox action
        self.action_show_toolbox = QAction(
            resources.icon_toolbox, tr("Show the toolbox"), self.iface.mainWindow()
        )
        self.action_show_toolbox.triggered.connect(self.show_toolbox)
        self.toolbar.addAction(self.action_show_toolbox)
        self.iface.addPluginToMenu(u"&TravelTime platform", self.action_show_toolbox)

        self.toolbar.addSeparator()

        # Express timemap action
        self.express_time_map_action = express.ExpressTimeMapAction(self)
        self.toolbar.addAction(self.express_time_map_action)

        # Express timefilter action
        self.express_time_filter_action = express.ExpressTimeFilterAction(self)
        self.toolbar.addAction(self.express_time_filter_action)

        # Express route action
        self.express_route_action = express.ExpressRouteAction(self)
        self.toolbar.addAction(self.express_route_action)

        self.toolbar.addSeparator()

        # Show tiles action
        self.action_show_tiles = QAction(
            resources.icon_tiles, tr("Add a background layer"), self.iface.mainWindow()
        )
        self.action_show_tiles.triggered.connect(self.show_tiles)
        self.toolbar.addAction(self.action_show_tiles)
        self.iface.addPluginToMenu(u"&TravelTime platform", self.action_show_tiles)

        # Show help actions
        self.action_show_help = QAction(
            resources.icon_help, tr("Help"), self.iface.mainWindow()
        )
        self.action_show_help.triggered.connect(self.show_help)
        self.toolbar.addAction(self.action_show_help)
        self.iface.addPluginToMenu(u"&TravelTime platform", self.action_show_help)

        # Show config actions
        self.action_show_config = QAction(
            resources.icon_config,
            tr("Configure TravelTime platform plugin"),
            self.iface.mainWindow(),
        )
        self.action_show_config.triggered.connect(self.show_config)
        self.toolbar.addAction(self.action_show_config)
        self.iface.addPluginToMenu(u"&TravelTime platform", self.action_show_config)

        # Add the provider to the registry
        QgsApplication.processingRegistry().addProvider(self.provider)

        # Show splash screen
        if not QSettings().value(
            "traveltime_platform/spashscreen_dontshowagain", False, type=bool
        ):
            self.show_splash()

    def unload(self):
        # Remove GUI elements
        del self.toolbar
        self.iface.removePluginMenu(u"&TravelTime platform", self.action_show_toolbox)
        self.iface.removePluginMenu(u"&TravelTime platform", self.action_show_tiles)
        self.iface.removePluginMenu(u"&TravelTime platform", self.action_show_config)
        self.iface.removePluginMenu(u"&TravelTime platform", self.action_show_help)

        # Remove the provider from the registry
        QgsApplication.processingRegistry().removeProvider(self.provider)

    def show_toolbox(self):
        toolBox = self.iface.mainWindow().findChild(QDockWidget, "ProcessingToolbox")
        if toolBox is None:
            self.iface.messageBar().pushMessage(
                "Error",
                tr(
                    "The Travel Time Platfrom plugin requires the Processing plugin. Please enable the processing plugin in the plugin manager."
                ),
                level=Qgis.Critical,
            )
            return
        toolBox.setVisible(True)
        toolBox.raise_()
        searchBox = toolBox.findChild(QgsFilterLineEdit, "searchBox")
        if searchBox.value() == "TravelTime platform":
            searchBox.textChanged.emit("TravelTime platform")
        else:
            searchBox.setValue("TravelTime platform")

    def show_tiles(self):
        self.tilesManager.add_tiles_to_browser()

        browser = self.iface.mainWindow().findChild(QDockWidget, "Browser")
        browser.setVisible(True)
        browser.raise_()

        # Get the XYZ item of the treeview
        treeview = (
            self.iface.mainWindow()
            .findChild(QDockWidget, "Browser")
            .findChild(QWidget, "mContents")
            .findChild(QSplitter)
            .widget(0)
            .findChild(QTreeView)
        )
        model = treeview.model()

        match = model.match(model.index(0, 0), Qt.DisplayRole, "XYZ Tiles")[0]
        treeview.collapseAll()
        treeview.clearSelection()
        treeview.expand(match)
        treeview.setCurrentIndex(match)
        treeview.scrollTo(match)

    def show_config(self):
        self.config_dialog.exec_()

    def show_splash(self):
        self.splash_screen.raise_()
        self.splash_screen.show()

    def show_help(self):
        self.help_dialog.show()

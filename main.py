import os.path
import requests
import functools

from qgis.PyQt.QtCore import Qt, QSettings, QCoreApplication, QTranslator, QSize
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
)
from qgis.core import Qgis, QgsApplication
from qgis.gui import QgsFilterLineEdit

from .provider import Provider
from .utils import tr, log
from . import resources
from . import auth
from . import ui
from . import auth
from . import tiles


class Main:
    def __init__(self, iface):
        self.iface = iface

        self.plugin_dir = os.path.dirname(__file__)

        locale = QSettings().value("locale/userLocale")[0:2]
        locale_path = os.path.join(
            self.plugin_dir, "i18n", "travel_time_platform_{}.qm".format(locale)
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
        self.tilesManager = tiles.TilesManager()

        self.toolbar = self.iface.addToolBar("Travel Time Platform Toolbar")

        # Logo
        button = QPushButton(resources.logo, "")
        button.setIconSize(QSize(112, 30))
        button.setFlat(True)
        button.pressed.connect(self.show_splash)
        self.toolbar.addWidget(button)
        self.toolbar.addSeparator()

        # Show toolbox action
        self.action_show_toolbox = QAction(
            resources.icon_general, tr("Show the toolbox"), self.iface.mainWindow()
        )
        self.action_show_toolbox.triggered.connect(self.show_toolbox)
        self.toolbar.addAction(self.action_show_toolbox)
        self.iface.addPluginToMenu(u"&Travel Time Platform", self.action_show_toolbox)

        # Add tiles
        tiles_menu = QMenu()
        for key, tile in self.tilesManager.tiles.items():
            action = QAction(tile["resource"], tile["label"], tiles_menu)
            action.triggered.connect(
                functools.partial(self.tilesManager.add_layer, key)
            )
            action.setEnabled(self.tilesManager.has_tiles)
            tiles_menu.addAction(action)
        if not self.tilesManager.has_tiles:
            action = QAction(tr("Request access to backgrounds"), tiles_menu)
            action.triggered.connect(lambda: self.tilesManager.request_access())
            tiles_menu.addAction(action)

        tiles_button = QToolButton()
        tiles_button.setToolTip(tr("Add background"))
        tiles_button.setIcon(resources.icon_tiles)
        tiles_button.setMenu(tiles_menu)
        tiles_button.setPopupMode(QToolButton.InstantPopup)

        # self.action_show_toolbox.triggered.connect(self.show_toolbox)
        self.toolbar.addWidget(tiles_button)
        # self.iface.addPluginToMenu(u"&Travel Time Platform", self.action_show_toolbox)
        self.toolbar.addSeparator()

        # Show help actions
        self.action_show_help = QAction(
            resources.icon_help, tr("Help"), self.iface.mainWindow()
        )
        self.action_show_help.triggered.connect(self.show_splash)
        self.toolbar.addAction(self.action_show_help)
        self.iface.addPluginToMenu(u"&Travel Time Platform", self.action_show_help)

        # Show config actions
        self.action_show_config = QAction(
            resources.icon_config,
            tr("Configure Travel Time Platform plugin"),
            self.iface.mainWindow(),
        )
        self.action_show_config.triggered.connect(self.show_config)
        self.toolbar.addAction(self.action_show_config)
        self.iface.addPluginToMenu(u"&Travel Time Platform", self.action_show_config)

        # Add the provider to the registry
        QgsApplication.processingRegistry().addProvider(self.provider)

        # Show splash screen
        if not QSettings().value(
            "travel_time_platform/spashscreen_dontshowagain", False, type=bool
        ):
            self.show_splash()

    def unload(self):
        # Remove GUI elements
        del self.toolbar
        self.iface.removePluginMenu(u"&Travel Time Platform", self.action_show_toolbox)
        self.iface.removePluginMenu(u"&Travel Time Platform", self.action_show_config)
        self.iface.removePluginMenu(u"&Travel Time Platform", self.action_show_help)

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
        searchBox = toolBox.findChild(QgsFilterLineEdit, "searchBox")
        if searchBox.value() == "Travel Time Platform":
            searchBox.textChanged.emit("Travel Time Platform")
        else:
            searchBox.setValue("Travel Time Platform")

    def show_config(self):
        self.config_dialog.exec_()

    def show_splash(self):
        self.splash_screen.raise_()
        self.splash_screen.show()

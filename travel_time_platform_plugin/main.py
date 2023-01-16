import contextlib
import io
import json
import os.path

import processing
from qgis.core import Qgis, QgsApplication
from qgis.gui import QgsFilterLineEdit
from qgis.PyQt.QtCore import (
    QCoreApplication,
    QLocale,
    QSettings,
    QSize,
    Qt,
    QTranslator,
)
from qgis.PyQt.QtGui import QGuiApplication
from qgis.PyQt.QtWidgets import (
    QAction,
    QDockWidget,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeView,
)

from . import express, resources, tests, tiles, ui
from .provider import Provider
from .utils import log, tr


class TTPPlugin:
    def __init__(self, iface):
        self.iface = iface

        self.plugin_dir = os.path.dirname(__file__)

        locale = QSettings().value("locale/userLocale") or QLocale().name() or "en"
        locale_path = os.path.join(
            self.plugin_dir, "i18n", f"traveltime_{locale[0:2]}.qm"
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

        self.toolbar = self.iface.addToolBar("TravelTime Toolbar")

        # Logo
        button = QPushButton(resources.banner_toolbar, "")
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
        self.iface.addPluginToMenu("&TravelTime", self.action_show_toolbox)

        # Rerun algorithm action
        self.action_rerun = QAction(
            resources.icon_rerun, tr("Run again"), self.iface.mainWindow()
        )
        self.action_rerun.triggered.connect(self.rerun_algorithm)
        self.toolbar.addAction(self.action_rerun)
        self.iface.addPluginToMenu("&TravelTime", self.action_rerun)
        self.action_rerun.setEnabled(False)

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

        # Express geoclick action
        self.express_geoclick_lineedit = QLineEdit()
        self.express_geoclick_action = express.ExpressGeoclickAction(
            self, self.express_geoclick_lineedit
        )
        self.toolbar.addWidget(self.express_geoclick_lineedit)
        self.toolbar.addAction(self.express_geoclick_action)

        self.toolbar.addSeparator()

        # Show tiles action
        self.action_show_tiles = QAction(
            resources.icon_tiles, tr("Add a background layer"), self.iface.mainWindow()
        )
        self.action_show_tiles.triggered.connect(self.show_tiles)
        self.toolbar.addAction(self.action_show_tiles)
        self.iface.addPluginToMenu("&TravelTime", self.action_show_tiles)

        # Show help actions
        self.action_show_help = QAction(
            resources.icon_help, tr("Help"), self.iface.mainWindow()
        )
        self.action_show_help.triggered.connect(self.show_help)
        self.toolbar.addAction(self.action_show_help)
        self.iface.addPluginToMenu("&TravelTime", self.action_show_help)

        # Show config actions
        self.action_show_config = QAction(
            resources.icon_config,
            tr("Configure TravelTime plugin"),
            self.iface.mainWindow(),
        )
        self.action_show_config.triggered.connect(self.show_config)
        self.toolbar.addAction(self.action_show_config)
        self.iface.addPluginToMenu("&TravelTime", self.action_show_config)

        # Show run tests
        self.action_run_tests = QAction(
            resources.icon_tests,
            tr("Run tests"),
            self.iface.mainWindow(),
        )
        self.action_run_tests.triggered.connect(self.run_tests)
        self.toolbar.addAction(self.action_run_tests)
        self.iface.addPluginToMenu("&TravelTime", self.action_run_tests)

        # Add the provider to the registry
        QgsApplication.processingRegistry().addProvider(self.provider)

        # Connect signals
        self.iface.initializationCompleted.connect(self.init_finished)
        self.iface.currentLayerChanged.connect(self.current_layer_changed)
        self.config_dialog.accepted.connect(self.config_changed)

        # Trigger signals
        self.current_layer_changed(self.iface.activeLayer())
        self.config_changed()
        if self.iface.mainWindow().isVisible():
            # If mainWindow is visible, it means init was already completed
            self.init_finished()

    def unload(self):
        # Remove GUI elements
        del self.toolbar
        self.iface.removePluginMenu("&TravelTime", self.action_show_toolbox)
        self.iface.removePluginMenu("&TravelTime", self.action_show_tiles)
        self.iface.removePluginMenu("&TravelTime", self.action_show_config)
        self.iface.removePluginMenu("&TravelTime", self.action_show_help)
        self.iface.removePluginMenu("&TravelTime", self.action_rerun)
        self.iface.removePluginMenu("&TravelTime", self.action_run_tests)

        # Remove the provider from the registry
        QgsApplication.processingRegistry().removeProvider(self.provider)

        # Disconnect actions
        self.iface.currentLayerChanged.disconnect(self.current_layer_changed)

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
        if searchBox.value() == "TravelTime":
            searchBox.textChanged.emit("TravelTime")
        else:
            searchBox.setValue("TravelTime")

    def rerun_algorithm(self):
        alg_id = self.iface.activeLayer().metadata().keywords()["TTP_ALGORITHM"][0]
        params = json.loads(
            self.iface.activeLayer().metadata().keywords()["TTP_PARAMS"][0]
        )
        self._dlg = processing.createAlgorithmDialog(alg_id, params)
        self._dlg.show()

    def show_tiles(self):
        self.tilesManager.add_tiles_to_browser()

        browser = self.iface.mainWindow().findChild(QDockWidget, "Browser")
        browser.setVisible(True)
        browser.raise_()

        # Get the XYZ item of the treeview
        treeview = browser.findChild(QTreeView)
        model = treeview.model()
        xyz_tiles_group_idx = model.match(
            model.index(0, 0),
            Qt.DisplayRole,
            "XYZ Tiles",
        )
        if len(xyz_tiles_group_idx) == 0:
            # Shouldn't happen, but let's play safe
            return

        # Fold everything and display it
        treeview.collapseAll()
        treeview.clearSelection()
        treeview.expand(xyz_tiles_group_idx[0])
        treeview.setCurrentIndex(xyz_tiles_group_idx[0])
        treeview.scrollTo(xyz_tiles_group_idx[0])

        # If tiles were loaded, selected it
        lux_tiles_idx = model.match(
            model.index(0, 0, xyz_tiles_group_idx[0]),
            Qt.DisplayRole,
            "TravelTime - Lux",
        )
        if len(lux_tiles_idx) == 0:
            # If not loaded (because missing API), good enough, we showed background tiles
            return

        # Display it
        treeview.setCurrentIndex(lux_tiles_idx[0])
        treeview.scrollTo(lux_tiles_idx[0])

    def show_config(self):
        self.config_dialog.exec_()

    def run_tests(self):

        box = QMessageBox(
            QMessageBox.Question,
            "Run software tests",
            "You are about to run automated software tests. There is usually no reason to run them, unless you want to share a report to track down issues that you may encounter.\n\n"
            "Warning:\n"
            "- the current project will be closed without saving\n"
            "- there may be some side-effects on your QGIS user profile\n"
            "- this will use your API quota\n"
            "- do not interact with QGIS while the tests run",
        )
        box.setInformativeText("Do you want to proceed ?")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)

        if box.exec_() != QMessageBox.Yes:
            return

        with io.StringIO() as buf:
            with contextlib.redirect_stdout(buf):
                result = tests.run_suite(stream=buf)
            output = buf.getvalue()

        log(tests.system_info(), "TravelTime tests output")
        log(output, "TravelTime tests output")

        success = result.wasSuccessful()

        if success:
            box = QMessageBox(
                QMessageBox.Information,
                "Success",
                f"All {result.testsRun} tests succeeded.",
            )
        else:
            box = QMessageBox(
                QMessageBox.Critical,
                "Failure",
                f"{len(result.errors) + len(result.failures)} tests failed out of {result.testsRun}.",
            )
        box.setInformativeText("Do you want to copy the report to the clipboard ?")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        if box.exec_() == QMessageBox.Yes:
            QGuiApplication.clipboard().setText(f"{tests.system_info()}\n{output}")

    def show_splash(self):
        self.splash_screen.raise_()
        self.splash_screen.show()

    def show_help(self):
        self.help_dialog.show()

    def init_finished(self):
        # Show splash screen
        if not QSettings().value(
            "traveltime_platform/spashscreen_dontshowagain", False, type=bool
        ):
            self.show_splash()

    def config_changed(self):
        visible = QSettings().value(
            "traveltime_platform/show_tests_button", False, type=bool
        )
        self.action_run_tests.setVisible(visible)

    def current_layer_changed(self, layer):
        self.action_rerun.setEnabled(
            layer is not None
            and hasattr(layer.metadata(), "keywords")
            and ("TTP_VERSION" in layer.metadata().keywords())
        )

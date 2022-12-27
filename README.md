# ![Travel Time Platform](travel_time_platform_plugin/resources/TravelTime_logo_horizontal.svg)

[![.github/workflows/tests.yml](https://github.com/traveltime-dev/traveltime-platform-qgis-plugin/actions/workflows/tests.yml/badge.svg)](https://github.com/traveltime-dev/traveltime-platform-qgis-plugin/actions/workflows/tests.yml)

This is the repository for the TravelTime platform plugin for QGIS.

This plugin intends to make the TravelTime platform API available for ues in QGIS through processing algorithms.

## Installation

This plugin is available in the official QGIS repository (you need to enable experimental plugins for beta releases).

## Documentation

The documentation is available here : https://qgis.traveltimeplatform.com/

## Bug reports

Please report any issue to the bug tracker.

## Contribute

### Release

Releases to the QGIS plugin repository are made by Github workflows upon creation of a Github release. Make sure to use semantic verisonning for the version name, to populate the changelog in metadata.txt, and to mark the release as `pre-release` if the release should be marked as experimental.

### Tests

Run the integrations tests with docker

```bash
# Copy the default config, then edit with your own API key
cp .env.example .env

# Run tests (headless)
docker-compose run tests

# Run tests (with visual feedback, on Windows only works under WSL)
docker-compose run tests-gui
```

These tests are run automatically in Github actions. The actions require two secrets to be set: `API_APP_ID` and `API_KEY`.

Alternatively, you can also run the tests from the QGIS desktop.


## Code style

Formatting is done with `pre-commit`. Please run `pip install pre-commit` and `pre-commit install` prior to contributing.

## Translations

To update the translations :

```
# Update the translations files
pylupdate5 i18n/traveltime_platform.pro

# Make modifications to *.ts files either manually or using QtLinguist

# Regenerate the .qm files
lrelease i18n/traveltime_platform_fr.ts
```

Note : under Windows, make sure you installed `qt5-devel` and `qt5-tools` (using osgeo4w installer) and run the above commands from the `OSGeo4W shell`. You will need to setup the shell for qt5 and python3 by running `o4w_env`, `qt5_env` and `py3_env` beforehand.

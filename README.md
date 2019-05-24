# ![resources/ttp_banner.svg](resources/ttp_banner_whitebackground.svg)

This is the repository for the TravelTime platform plugin for QGIS.

This plugin intends to make the TravelTime platform API available for ues in QGIS through processing algorithms.

## Installation

Once released, this plugin will be available in the official QGIS repository.

In the meantime, you need to download the repository as zip a file and install it manually from the plugin manager.

## Usage

Please read the plugin documentation, available both from within the plugin itself or [online](https://docs.traveltimeplatform.com/qgis). ( TODO : fix link )

## Bug reports

Please report any issue to the bug tracker.

## Limitations

Currently, only the
[Time Map endpoint](http://docs.traveltimeplatform.com/reference/time-map/) is implemented.

Currently, only 10 searches can be made per API query.

## Development

To update the translations :

```
# Update the translations files
pylupdate5 i18n/traveltime_platform.pro

# Make modifications to *.ts files either manually or using QtLinguist

# Regenerate the .qm files
lrelease i18n/traveltime_platform_fr.ts
```

Note : under Windows, make sure you installed `qt5-devel` and `qt5-tools` (using osgeo4w installer) and run the above commands from the `OSGeo4W shell`. You will need to setup the shell for qt5 and python3 by running `o4w_env`, `qt5_env` and `py3_env` beforehand.

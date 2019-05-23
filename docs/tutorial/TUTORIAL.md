# Tutorial

This tutorial covers usage of the new Travel Time Platform Plugin for QGIS.

## Introduction

### What it is

Travel time is much more accurate than distance to take informed decisions, such as where to locate a new office, what type of transport to choose, or at what time a meeting should start.

The Travel Time Platform Plugin for QGIS is a brand new plugin that add several algorithms that aim to allow this type of analysis right in QGIS. It works by making use of the Travel Time Platform API, an extremely fast web service for such computations.

### What we'll cover

During this tutorial, we'll cover :
- Installation
- Setup,
- Basic usage

Then, we'll go through a series of use cases which demonstrate most of the plugin's capabilities :
- Making an Isochrones map
- Comparing transportation modes
- Mapping the effects of rush hour
- Picking the best venue for an event based on travel times
- Getting routing information
- Other useful information

### Installation and setup

To install the plugin, open the QGIS plugin manager, search for `Travel Time Platform`, and click on install.

[INSERT SCREENSHOT]

If the plugin was installed correctly, you should see a new tool bar.

[INSERT SCREENSHOT]

Before being able to use the plugin, you need to get a free API key. This is required to be able to use the Travel Time web service. Open the configuration dialog, and click on the `Get free API key button`.

[INSERT SCREENSHOT]

This will open a web page. Fill in the form, and you will get your API key in your inbox. Just copy and paste the `Application ID` and the `API Key` back in the configuration dialog.

> Just a note : each API key has a limited quota of requests that can be done in a certain amount of time. This means that your API key may be blocked for some time if you make too many requests over a short period of time. To avoid hitting this limit without noticing, the plugin has a warning feature, that will notify you after a certain number of queries has been made. You can configure or even disable this limit in the same configuration dialog.

The plugin is now ready for use !


### Preparing for the tutorial

For the tutorial, we'll use a sample dataset that you can download here : [INSERT DOWNLOAD LINK]

It consists of :
- roads (we'll use this as background)
- buildings (we'll use this as background)
- hotels (a point layer reprensenting hotels)
- stations (a point layer representing public transport stations)
- xxx

This data was obtained from OpenStreetMap. You could use the QuickOSM QGIS plugin to download this type of data in QGIS.

## General

The main toolbar has the following buttons :

- [INSERT ICON] : open the list of algorithms in the Processing Toolbox.
- [INSERT ICON] : add a background layer
- [INSERT ICON] : open the help dialog
- [INSERT ICON] : open the configuration dialog

The actual feature of the plugins are located in the QGIS Processing Toolbox, alongside all other powerful QGIS algorithms. This comes with several benefits that we will cover later, such as the ability to run these algorithms in batch or the create complex workflows.

Let's just have a look at this before we actually get started. Click on the [INSERT ICON] open list button.

[INSERT SCREENSHOT]

The algorithms are sorted in three groups. The **advanced algorithms** are the most powerful. They match very closely to the Travel Time webservice, and are very customizable. So much, that in the end, for most cases, they are a bit of an overkill.  That's why the **simplified algorithms** group exist. It contains the very same algorithms, but with only a subset of parameters. Internally, the corresponding advanced algorithm will be called. The **utilities** group adds some small utilities that deal with geocoding, which can be useful to transform adresses in geographical points.

## Time map

### Making an Isochrones map

- isochrones map : show how well connected differents POI are (e.g. when choose a location for a new store) => (timemapsimple, batch mode)

### Comparing transportation modes

- bike vs public trspt vs car : map areas that are reachable faster by bike or by car from one POI => (timemapsimple, timemapadvanced)

### Mapping the effects of rush hour

- rush hour : show how rush hours affects travel times => (timemapsimple)

## Time filter

### Planning an event
- for an event => (timefiltersimpe)
  - filter out hotels from which it's not possible to arrive at 8h at the confrence
  - what if the conference starts at 10 ?

## Route

### Routing information

- print out detailed route instructions to go from hotel to conference => (iterate feature)

## Going further

- tiles
- show advanced algorithms
- show inclusion in processing modeler
- show API doc

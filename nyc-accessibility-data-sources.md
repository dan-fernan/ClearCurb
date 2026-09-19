# NYC Accessibility Data Sources — Wheelchair Route Planner

Reference links for datasets used in the accessible routing project.

## Sidewalk & Curb Geometry

- **Curbs (NYC Planimetric Database)**
  https://data.cityofnewyork.us/City-Government/NYC-Planimetric-Database-Curbs/ikvd-dex8

- **Sidewalk polygons (NYC Planimetric Database)**
  Search "NYC Planimetric Database Sidewalk" on data.cityofnewyork.us — confirm the exact dataset ID before building the pipeline around it.

## Sidewalk Condition / Defects

- **Sidewalk Management Database – Inspection**
  https://data.cityofnewyork.us/Transportation/Sidewalk-Management-Database-Inspection/dntt-gqwq

- **Sidewalk Management Database – Violations**
  https://data.cityofnewyork.us/Transportation/Sidewalk-Management-Database-Violations/6kbp-uz6m

- **Sidewalk Management Database – Built (repair history)**
  https://data.cityofnewyork.us/Transportation/Sidewalk-Management-Database-Built/ugc8-s3f6

## Streets / Step Streets

- **LION Single Line Street Base Map**
  https://home.nyc.gov/site/planning/data-maps/open-data/dwn-lion.page
  (Look for `RW_TYPE = 7` to flag step streets.)

## Elevation

- **NYC Planimetric Database – Elevation Points**
  https://data.cityofnewyork.us/Transportation/NYC-Planimetric-Database-Elevation-Points/szwg-xci6

- **NY State Elevation Program (1m LiDAR DEM, statewide)**
  https://gis.ny.gov/elevation

- **NYC Bare-Earth DEM (ArcGIS ImageServer)**
  https://elevation.its.ny.gov/arcgis/rest/services/NYC_TopoBathymetric2017_1_foot/ImageServer

## Crowdsourced Accessibility Data (supplement)

- **Project Sidewalk** (multi-city — check site for city selector)
  https://sidewalk-sea.cs.washington.edu/

## API Access Pattern (Socrata datasets)

Once on a dataset page, the API endpoint follows this pattern:

```
https://data.cityofnewyork.us/resource/{dataset-id}.json?$limit=1000
```

Example (Curbs):
```
https://data.cityofnewyork.us/resource/ikvd-dex8.json?$limit=1000
```

**App token (recommended before the hackathon):**
Free Socrata account, raises rate limit above the anonymous default.
https://data.cityofnewyork.us/profile/app_tokens

## Coordinate Reference Systems (unit cheat sheet)

| Stage | CRS | Units |
|---|---|---|
| As-served by Socrata | EPSG:4326 | degrees (lat/long) |
| NYC native/source projection | EPSG:2263 (State Plane, Long Island) | US survey feet |
| Elevation (DEM) | NAD83 / NAVD88 | US survey feet |

Reproject to EPSG:2263 before any distance/area/grade calculations, then convert back to EPSG:4326 for map display.

---
*Note: Curbs, Inspection, Violations, Built, and Elevation Points links were verified via search. Re-confirm each link directly before building a pipeline around it, since dataset IDs on NYC Open Data occasionally change.*

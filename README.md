# toronto-osm-washroom-import
 Analysis and prep files for importing City of Toronto washrooms into OpenStreetMap

## Set Up

This project uses poetry to manage python packages and the virtual environment. Please make sure to install poetry using the instructions here: [Poetry Documentation](https://python-poetry.org/docs/).

## Running

Run scripts:

```bash
$ poetry run python generate-imports.py
```

Format code:

```bash
$ poetry run black .
```

## Data Profiling - [Park Washroom Facilities](https://open.toronto.ca/dataset/washroom-facilities/)

As of 2024-07-21, the dataset included 418 features.

Columns:
- _id: Unique row identifier for Open Data database
- id: Parks, Forestry and Recreation Unique Identifier of the [park or community centre the washroom is in]
- asset_id: Parks, Forestry and Recreation Unique Identifier of the [washroom facility]
- location: Name of the [park or community centre]
- alternative_name: Is comprised of the name of the [park or community centre] and a descriptor of the location
- type: Ex: Washroom Building [n=344], Portable Toilet [n=74]
- accessible: Provides a list of accessible features, if available. Examples:
  - Entrance at Grade [n=89]
  - Accessible Stall [n=79]
  - Child Change Table [n=33]
  - Entrance Access Ramp [n=19]
  - Automatic Door Opener [n=16]
  - Adult Change Table [n=1]
  - 9 a.m. to 10 p.m. [n=1] - **likely an error in original data, should be "hours" value**
- hours: Hours of Operation, if outside of Park hours. Examples:
  - 9 a.m. to 10 p.m. [n=167]
  - View centre hours [n=101]
  - View outdoor rink hours [n=23]
  - View outdoor pool hours [n=23]
  - View facility hours [n=9]
  - 9 a.m. to 5 p.m. [n=2]
  - 9 a.m. to 7:30 p.m. [n=2]
  - View centre hours. [n=2]
  - 6:30 a.m. to 11:30 p.m. [n=1]
  - View the facility hours [n=1]
  - View arena hours [n=1]
- location_details: A detailed description of where to find the asset
- url: A link to the webpage of the [park or community centre]
- address: Street address of the park, where the drinking water source is located. [n.b. excludes city, province, or postal code]
- PostedDate: Date status was posted
- AssetName: This asset's name [n.b. almost identical to alternative_name, but has some minor differences in n=22 records]
- Reason: Reason for a particular status. Examples:
  - Closed for the Season [n=31]
  - Maintenance/Repairs [n=13]
  - Technical Issues [n=4]
  - Men's Washroom Closed, Women's Washroom Open [n=3]
  - Planned Closure [n=1]
  - Women's Washroom Closed, Men's Washroom Open [n=1]
- Comments: Open field for comments on this asset
- Status:
  - 0 = closed [n=44]
  - 1 = open [n=358]
  - 2 = service alert [n=16]
- geometry: point or polygon

Filtering decisions:
- **type:** exclude portable toilets, per ["Don't map... temporary features"](https://wiki.openstreetmap.org/wiki/Good_practice#Don't_map_temporary_events_and_temporary_features)
- **Status:** only include status 1 (open). Status 2 could be considered for import, but would require manual review to determine whether the washroom is functioning with minor issues (e.g. sink out of order) or if it should be considered effectively closed.

Will have to decide when reviewing:
- "building": "toilets" if drawn
- "indoor" especially for toilets within community centres

Can only determine via survey:
- seasonal hours
- gender_segregated

Not including:
- name
- address information

**TODO - is conflation menu confusing for source vs target? Would be rationale for pre-coflating (plus reduces manual work)**

**TODO - assert that status=1 facilities have no Comments value**


## Data Profiling - [Street Furniture - Public Washroom](https://open.toronto.ca/dataset/street-furniture-public-washroom/)

This dataset only includes four features, so it would be easier to address any needed edits manually:

- SE of Lakeshore Blvd and Net Dr - [exists in OSM](https://www.openstreetmap.org/way/703258474)
- SE corner of Fleet St and Strachan Ave - does not exist in OSM 
- NW corner of Rees St and Queen's Quay W - [exists in OSM](https://www.openstreetmap.org/node/2617630911)
- SE corner of Lakeshore Blvd and Northern Dancer Blvd - [exists in OSM](https://www.openstreetmap.org/way/1017243072)
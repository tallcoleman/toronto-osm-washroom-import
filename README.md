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
- type: Ex: Washroom [n=344], Portable Toilet [n=74]
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

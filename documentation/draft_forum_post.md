Include the tags import and import-proposal.

Subject: Proposed import of City of Toronto Parks and Recreation Washroom Facilities


# Toronto Public Washroom Import
Hello Canada, we are proposing to import the Toronto Park Washroom Facilities dataset, sourced from City of Toronto Open Data.


## Documentation
This is the wiki page for our import: **TODO ADD**
wiki.openstreetmap.org/wiki/

This is the source dataset's website:
https://open.toronto.ca/dataset/washroom-facilities/

Transformation scripts, files to be imported for each changeset, and some example .osm files following the process outlined on our proposal import wiki page can be found at our GitHub repository here: https://github.com/tallcoleman/toronto-osm-washroom-import


## License
We have checked that this data is compatible with the ODbL.
This data is distributed under the [Open Government License - Toronto](https://open.toronto.ca/open-data-license/), which has been previously approved by the DWG (see: [osmfoundation.org - OGL Canada and local variants](https://osmfoundation.org/wiki/OGL_Canada_and_local_variants))


## Abstract

The goal of this project is to import the locations and details of public washrooms in Toronto, Ontario, Canada using open data provided by the City of Toronto. 

[Park Washroom Facilities](https://open.toronto.ca/dataset/washroom-facilities/) includes the location and key details of 418 City-run public washrooms in parks and community centres. This dataset will be imported in this project. 

We expect to import around 300 data points after filtering for quality, type, and status. Of these, around 100 will be conflated with existing washroom locations and around 200 will be locations that were previously un-mapped. These will be broken up into 25 changesets based on City of Toronto ward.

In addition to the 300 data points in the main import sets, there are also an additional up to 20 washroom locations with service alerts that will be manually reviewed and added or conflated if appropriate. (Service alerts range from total closure of the washroom for one gender to a single broken stall or sink.)

The import will be a two-part process:

* Transformation of the source data into OSM tags, using the [script in our GitHub repository](https://github.com/tallcoleman/toronto-osm-washroom-import)
* Manual conflation, review, and import using JOSM and following the protocol we have outlined on our import proposal wiki page. This process is designed to retain the geometry, edit history, and original tags (where relevant) for City washrooms that have already been mapped.

More information about the tag transformation logic and the instructions for JOSM conflation can be found on our import proposal wiki page.

If you have any questions or suggestions to improve the import plan, please let us know!

Many thanks - **TODO NAMES**
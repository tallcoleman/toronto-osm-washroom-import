import json
import os
import requests

import geopandas as gpd

from resources.openstreetmap import (
    query_overpass,
    feature_from_element,
)
from resources.torontoopendata import request_tod_gdf

# get existing washrooms in OSM
# get city open data (can you ignore the street furniture source?)


def generate_imports():
    current_washrooms = get_current_washrooms()
    current_washrooms_gdf = get_current_washrooms_gdf(current_washrooms)
    pfr_washrooms = get_pfr_washrooms()


def get_current_washrooms():
    washroom_query = """
        [out:json][timeout:25];
        area["official_name"="City of Toronto"]->.toArea;
        (
        nwr["amenity"="toilets"](area.toArea);
        nwr["building"="toilets"](area.toArea);
        );
        out geom meta;
    """
    current_washrooms = query_overpass(washroom_query)

    os.makedirs("source_data", exist_ok=True)
    with open("source_data/current_washrooms.json", "w") as f:
        json.dump(current_washrooms, f, indent=2)

    return current_washrooms


def get_current_washrooms_gdf(current_washrooms):
    current_washrooms_gdf = gpd.GeoDataFrame.from_features(
        {
            "type": "FeatureCollection",
            "features": [
                feature_from_element(x) for x in current_washrooms["elements"]
            ],
        },
        crs=current_washrooms["crs"]["properties"]["name"],
    )
    with open("source_data/current_washrooms.geojson", "w") as f:
        f.write(
            current_washrooms_gdf.to_json(
                na="drop",
                drop_id=True,
                indent=2,
            )
        )

    return current_washrooms_gdf


def get_pfr_washrooms():
    pfr_washrooms = request_tod_gdf(
        dataset_name="washroom-facilities",
        resource_id="6d848f38-45a3-41e8-9783-804385ec5a16",
    )
    return pfr_washrooms


if __name__ == "__main__":
    generate_imports()

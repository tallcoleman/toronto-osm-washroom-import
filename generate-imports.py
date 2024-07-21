import json
import os
import requests

import geopandas as gpd

from resources.openstreetmap import (
    query_overpass,
    feature_from_element,
)

# get existing washrooms in OSM
# get city open data (can you ignore the street furniture source?)


def generate_imports():
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


if __name__ == "__main__":
    generate_imports()

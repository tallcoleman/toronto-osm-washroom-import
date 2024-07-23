import json
import os
import re

import geopandas as gpd
import pandas as pd

from resources.openstreetmap import (
    query_overpass,
    feature_from_element,
)
from resources.torontoopendata import request_tod_gdf

# get existing washrooms in OSM
# get city open data (can you ignore the street furniture source?)


def generate_imports():
    os.makedirs("source_data", exist_ok=True)
    os.makedirs("to_import", exist_ok=True)

    current_washrooms = get_current_washrooms()
    current_washrooms_gdf = get_current_washrooms_gdf(current_washrooms)
    pfr_washrooms = get_pfr_washrooms()
    pfr_washrooms_osm = get_pfr_washrooms_osm(pfr_washrooms["gdf"])


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
    with open("source_data/pfr_washrooms.geojson", "w") as f:
        f.write(
            pfr_washrooms["gdf"]
            .assign(
                PostedDate=pfr_washrooms["gdf"]["PostedDate"].dt.strftime(
                    "%Y-%m-%dT%H:%M:%S.%f%z"
                )
            )
            .to_json(
                na="drop",
                drop_id=True,
                indent=2,
            )
        )
    with open("source_data/pfr_washrooms_meta.geojson", "w") as f:
        json.dump(pfr_washrooms["metadata"], f, indent=2)
    return pfr_washrooms


def get_pfr_washrooms_osm(gdf):
    original_cols = gdf.columns.drop("geometry")
    gdf_filtered = gdf[(gdf["type"] == "Washroom Building") & (gdf["Status"] == "1")]

    def pattern_search(pattern):
        def f(asset_name):
            match = re.search(pattern, asset_name, re.IGNORECASE)
            return "yes" if match != None else pd.NA

        return f

    def get_unisex(asset_name):
        match = re.search(
            r"\bmen's\b|\bmale\b|\bwomen's\b|\bfemale\b", asset_name, re.IGNORECASE
        )
        return "yes" if match == None else pd.NA

    def get_changing_table(accessible: str):
        return "yes" if "Child Change Table" in accessible else pd.NA

    def get_changing_table_adult(accessible: str):
        return "yes" if "Adult Change Table" in accessible else pd.NA

    def get_wheelchair(accessible: str):
        if (
            ("Entrance at Grade" in accessible)
            or ("Entrance Access Ramp" in accessible)
        ) and ("Accessible Stall" in accessible):
            return "yes"
        else:
            return pd.NA

    def get_toilets_wheelchair(accessible: str):
        return "yes" if "Accessible Stall" in accessible else pd.NA

    def get_wheelchair_description(accessible: str):
        if str(get_wheelchair(accessible)) != "yes":
            return pd.NA
        features = [
            "entrance at grade" if "Entrance at Grade" in accessible else None,
            "entrance access ramp" if "Entrance Access Ramp" in accessible else None,
            "automatic door opener" if "Automatic Door Opener" in accessible else None,
            "accessible stall" if "Accessible Stall" in accessible else None,
            "child change table" if "Child Change Table" in accessible else None,
            "adult change table" if "Adult Change Table" in accessible else None,
        ]
        return (
            f"Accessible features: {", ".join([x for x in features if x is not None])}"
        )

    def get_opening_hours(hours):
        # TODO only apply this if park washroom - need to import facility info
        if hours == "9 a.m. to 10 p.m.":
            return "May-Oct 09:00-22:00"
        elif hours == "9 a.m. to 5 p.m.":  # riverdale farm
            return "09:00-17:00"
        elif (
            hours == "9 a.m. to 7:30 p.m."
        ):  # TODO note on little norway indicates the bathroom closes at 5:30pm; but this park is currently filtered out by status
            return "09:00-19:30"
        elif hours == "6:30 a.m. to 11:30 p.m.":  # Jack Layton Ferry terminal
            return "06:30-23:30"
        else:
            return pd.NA

    def get_note(row):
        prompts = []
        if str(get_unisex(row["AssetName"])) == "yes":
            prompts.append("gender_segregated=yes/no")
        # TODO add park check here
        if row["hours"] == "9 a.m. to 10 p.m.":
            "is this washroom open in the winter? If yes, opening_hours are likely May-Oct Mo-Su 09:00-22:00; Nov-Apr Mo-Su 09:00-20:00"
        prompt_string = "; ".join(prompts)
        if len(prompt_string) > 0:
            return f"Please survey to determine: {prompt_string}"
        else:
            return pd.NA

    gdf_normalized = (
        gdf_filtered.assign(
            **{
                "amenity": "toilets",
                "access": "yes",
                "fee": "no",
                "male": gdf_filtered["AssetName"].apply(
                    pattern_search(r"\bmen's\b|\bmale\b")
                ),
                "female": gdf_filtered["AssetName"].apply(
                    pattern_search(r"\bwomen's\b|\bfemale\b")
                ),
                "unisex": gdf_filtered["AssetName"].apply(get_unisex),
                "toilets:disposal": "flush",
                "toilets:handwashing": "yes",
                "changing_table": gdf_filtered["accessible"]
                .astype(str)
                .apply(get_changing_table),
                "changing_table:adult": gdf_filtered["accessible"]
                .astype(str)
                .apply(get_changing_table_adult),
                "wheelchair": gdf_filtered["accessible"]
                .astype(str)
                .apply(get_wheelchair),
                "toilets:wheelchair": gdf_filtered["accessible"]
                .astype(str)
                .apply(get_toilets_wheelchair),
                "wheelchair:description": gdf_filtered["accessible"]
                .astype(str)
                .apply(get_wheelchair_description),
                "operator": "City of Toronto",
                "opening_hours": gdf_filtered["hours"]
                .astype(str)
                .apply(get_opening_hours),
                "note": gdf_filtered[["AssetName", "hours"]]
                .astype(str)
                .apply(
                    get_note,
                    axis=1,
                ),
                "ref:open.toronto.ca:washroom-facilities:asset_id": gdf_filtered[
                    "asset_id"
                ].astype(str),
            }
        )
        .drop(original_cols, axis=1)
        .explode(index_parts=False)  # convert MultiPoint to Point
    )
    with open("to_import/pfr_to_import.geojson", "w") as f:
        f.write(
            gdf_normalized.to_json(
                na="drop",
                drop_id=True,
                indent=2,
            )
        )
    return gdf_normalized


if __name__ == "__main__":
    generate_imports()

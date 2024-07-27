import json
import os
import re

import geopandas as gpd
import pandas as pd
import pandera as pa

from resources.openstreetmap import (
    query_overpass,
    feature_from_element,
)
from resources.torontoopendata import request_tod_gdf, TODResponse


def generate_imports():
    # generate output directories if needed
    os.makedirs("source_data", exist_ok=True)
    os.makedirs("to_import", exist_ok=True)

    # get amenity=toilets currently in openstreetmap
    current_washrooms = get_current_washrooms()
    current_washrooms_gdf = get_current_washrooms_gdf(current_washrooms)

    # get city open data
    pfr_washrooms = get_pfr_washrooms()
    pfr_facilities = get_pfr_facilities()
    pfr_facility_types = get_pfr_facility_types(pfr_facilities["gdf"])

    # merge facility info into city washrooms dataset
    pfr_washrooms_type = pd.merge(
        pfr_washrooms["gdf"],
        pfr_facility_types.rename(
            columns={"LOCATIONID": "parent_id", "TYPE": "parent_type"}
        ),
        how="left",
        on="parent_id",
    )

    # normalize city washroom data into osm tags and organize by ward
    pfr_washrooms_osm = get_pfr_washrooms_osm(pfr_washrooms_type)
    wards = get_wards_gdf()
    pfr_washrooms_wards = pfr_washrooms_osm.sjoin(wards, how="left").drop(
        ["index_right", "ward_code", "ward_name"], axis=1
    )
    pfr_by_ward = {k: v for k, v in pfr_washrooms_wards.groupby("ward_full")}

    # save files to use in JOSM import
    for ward_full, ward_gdf in pfr_by_ward.items():
        os.makedirs(f"to_import/by_ward/{ward_full}/", exist_ok=True)
        with open(
            f"to_import/by_ward/{ward_full}/{ward_full}_washrooms.geojson", "w"
        ) as f:
            f.write(
                ward_gdf.drop(["ward_full", "ward_bbox"], axis=1).to_json(
                    na="drop",
                    drop_id=True,
                    indent=2,
                )
            )
        with open(
            f"to_import/by_ward/{ward_full}/{ward_full}_buildings_query.txt", "w"
        ) as f:
            f.write(get_building_query(ward_gdf["ward_bbox"].iloc[0]))
        with open(
            f"to_import/by_ward/{ward_full}/{ward_full}_toilets_query.txt", "w"
        ) as f:
            f.write(get_washrooms_query(ward_gdf["ward_bbox"].iloc[0]))

    # generate summary statistics
    changesets = pd.DataFrame(
        {
            "ward_full": [k for k in pfr_by_ward.keys()],
            "size": [len(v) for v in pfr_by_ward.values()],
        }
    )
    summary = []
    summary.append("\n===== SUMMARY =====\n")
    summary.append(
        f"{len(pfr_washrooms["gdf"])} data points in original Park Washroom Facilities dataset"
    )
    summary.append(f"{len(pfr_washrooms_osm)} data points in normalized import dataset")
    summary.append(
        f"{len(changesets)} changesets generated, largest has {changesets["size"].max()} points, and smallest has {changesets["size"].min()} points"
    )
    summary.append(changesets.to_string(index=False))
    print("\n".join(summary))


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


def get_pfr_washrooms() -> TODResponse:
    pfr_washrooms = request_tod_gdf(
        dataset_name="washroom-facilities",
        resource_id="6d848f38-45a3-41e8-9783-804385ec5a16",
    )
    pfr_washrooms["gdf"] = (
        pfr_washrooms["gdf"]
        .rename(columns={"id": "parent_id"})
        .astype({"parent_id": str})
    )

    # validate city data and throw errors if input assumptions have changed
    def check_accessible(accessible: pd.Series):
        known_values = [
            pd.NA,
            "Entrance at Grade",
            "Accessible Stall",
            "Child Change Table",
            "Entrance Access Ramp",
            "Automatic Door Opener",
            "Adult Change Table",
            # known error; ignored by the get_wheelchair_description function:
            "9 a.m. to 10 p.m.",
        ]
        accessible_lists = accessible.replace("", pd.NA).str.split(", ")
        return accessible_lists.apply(lambda x: pd.Series(x).isin(known_values).all())

    schema = pa.DataFrameSchema(
        {
            # REQUIRED COLUMNS
            "parent_id": pa.Column(str, required=True),
            "asset_id": pa.Column("int32", unique=True, required=True),
            "type": pa.Column(
                str,
                required=True,
                checks=pa.Check.isin(["Washroom Building", "Portable Toilet"]),
            ),
            "accessible": pa.Column(
                str,
                nullable=True,
                required=True,
                checks=pa.Check(check_accessible),
            ),
            "hours": pa.Column(
                str,
                nullable=True,
                required=True,
                checks=pa.Check.isin(
                    [
                        "9 a.m. to 10 p.m.",
                        "View centre hours",
                        "View outdoor rink hours",
                        "View outdoor pool hours",
                        "View facility hours",
                        "9 a.m. to 5 p.m.",
                        "9 a.m. to 7:30 p.m.",
                        "View centre hours.",
                        "6:30 a.m. to 11:30 p.m.",
                        "View the facility hours",
                        "View arena hours",
                    ]
                ),
            ),
            "location_details": pa.Column(str, required=True),
            "AssetName": pa.Column(str, required=True),
            "geometry": pa.Column(
                "geometry",
                required=True,
                # check that there is only one coordinate pair per MultiPoint
                checks=pa.Check(lambda s: s.apply(lambda x: len(x.geoms) == 1)),
            ),
            "Reason": pa.Column(str, nullable=True, required=True),
            "Comments": pa.Column(str, nullable=True, required=True),
            "Status": pa.Column(
                str,
                required=True,
                checks=pa.Check.isin(["0", "1", "2"]),
            ),
            # OPTIONAL COLUMNS
            "_id": pa.Column("int32"),
            "location": pa.Column(str),
            "alternative_name": pa.Column(str),
            "url": pa.Column(str),
            "address": pa.Column(str),
            "PostedDate": pa.Column("datetime64"),
        }
    )
    schema.validate(pfr_washrooms["gdf"], lazy=True)

    # save validated city data
    with open("source_data/pfr_washrooms.geojson", "w") as f:
        f.write(
            pfr_washrooms["gdf"]
            .assign(
                PostedDate=pfr_washrooms["gdf"]["PostedDate"].dt.strftime(
                    "%Y-%m-%dT%H:%M:%S.%f%z"
                )
            )
            .to_json(na="drop", drop_id=True, indent=2)
        )
    with open("source_data/pfr_washrooms_meta.geojson", "w") as f:
        json.dump(pfr_washrooms["metadata"], f, indent=2)
    return pfr_washrooms


def get_pfr_facilities() -> TODResponse:
    pfr_facilities = request_tod_gdf(
        dataset_name="parks-and-recreation-facilities",
        resource_id="f6cdcd50-da7b-4ede-8e60-c3cdba70b559",
    )

    # validate data
    schema = pa.DataFrameSchema(
        {
            "LOCATIONID": pa.Column(str, required=True, unique=False),
            "TYPE": pa.Column(
                str, required=True, checks=pa.Check.isin(["Park", "Community Centre"])
            ),
        }
    )
    schema.validate(pfr_facilities["gdf"])

    # save validated city data
    with open("source_data/pfr_facilities.geojson", "w") as f:
        f.write(pfr_facilities["gdf"].to_json(na="drop", drop_id=True, indent=2))
    with open("source_data/pfr_facilities_meta.geojson", "w") as f:
        json.dump(pfr_facilities["metadata"], f, indent=2)
    return pfr_facilities


def get_pfr_facility_types(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return (
        gdf[["LOCATIONID", "TYPE"]]
        .sort_values("TYPE", ascending=True)
        .groupby("LOCATIONID", as_index=False)
        .agg(lambda x: "|".join(set(x)))
    )


def get_pfr_washrooms_osm(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    original_cols = gdf.columns.drop("geometry")

    # filter city data and confirm that filtered data does not contain Reason or Comments columns
    gdf_filtered = gdf[(gdf["type"] == "Washroom Building") & (gdf["Status"] == "1")]
    schema = pa.DataFrameSchema(
        {
            "Reason": pa.Column(
                str,
                nullable=True,
                checks=pa.Check.equal_to(pd.NA),
            ),
            "Comments": pa.Column(
                str,
                nullable=True,
                checks=pa.Check.equal_to(pd.NA),
            ),
        }
    )
    schema.validate(gdf_filtered, lazy=True)

    # normalize city data to openstreetmap tags
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
        if accessible == "None":
            return "no"
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

    def get_opening_hours(row):
        hours = row["hours"]
        parent_type = row["parent_type"]
        if hours == "9 a.m. to 10 p.m." and parent_type == "Park":
            return "May-Oct 09:00-22:00"
        elif hours == "9 a.m. to 10 p.m." and parent_type == "Community Centre":
            return "09:00-22:00"
        elif hours == "9 a.m. to 10 p.m." and parent_type == "Community Centre|Park":
            return pd.NA
        # Riverdale Farm:
        elif hours == "9 a.m. to 5 p.m.":
            return "09:00-17:00"
        # Coronation Park, 711 Lake Shore Blvd  W:
        elif hours == "9 a.m. to 7:30 p.m.":
            return "09:00-19:30"
        # Jack Layton Ferry terminal:
        elif hours == "6:30 a.m. to 11:30 p.m.":
            return "06:30-23:30"
        else:
            return pd.NA

    def get_note(row):
        prompts = []
        if str(get_unisex(row["AssetName"])) == "yes":
            prompts.append("gender_segregated=yes/no")
        if row["hours"] == "9 a.m. to 10 p.m." and row["parent_type"] == "Park":
            prompts.append(
                "is this washroom open in the winter? If yes, opening_hours are likely May-Oct Mo-Su 09:00-22:00; Nov-Apr Mo-Su 09:00-20:00"
            )
        if (
            row["hours"] == "9 a.m. to 10 p.m."
            and row["parent_type"] == "Community Centre|Park"
        ):
            prompts.append("opening hours")
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
                "changing_table": (
                    gdf_filtered["accessible"].astype(str).apply(get_changing_table)
                ),
                "changing_table:adult": (
                    gdf_filtered["accessible"]
                    .astype(str)
                    .apply(get_changing_table_adult)
                ),
                "wheelchair": (
                    gdf_filtered["accessible"].astype(str).apply(get_wheelchair)
                ),
                "toilets:wheelchair": (
                    gdf_filtered["accessible"].astype(str).apply(get_toilets_wheelchair)
                ),
                "wheelchair:description": (
                    gdf_filtered["accessible"]
                    .astype(str)
                    .apply(get_wheelchair_description)
                ),
                "operator": "City of Toronto",
                "opening_hours": (
                    gdf_filtered[["hours", "parent_type"]]
                    .astype(str)
                    .apply(get_opening_hours, axis=1)
                ),
                "description": gdf_filtered["location_details"],
                "note": (
                    gdf_filtered[["AssetName", "hours", "parent_type"]]
                    .astype(str)
                    .apply(get_note, axis=1)
                ),
                "ref:open.toronto.ca:washroom-facilities:asset_id": (
                    gdf_filtered["asset_id"].astype(str)
                ),
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


def get_wards_gdf() -> gpd.GeoDataFrame:
    wards = request_tod_gdf(
        dataset_name="city-wards",
        resource_id="737b29e0-8329-4260-b6af-21555ab24f28",
    )
    wards_formatted = (
        wards["gdf"][["AREA_SHORT_CODE", "AREA_NAME", "geometry"]]
        .assign(
            ward_full=[
                f"{x.AREA_NAME} ({x.AREA_SHORT_CODE})"
                for x in wards["gdf"].itertuples()
            ]
        )
        .assign(
            ward_bbox=[
                f"{x.miny},{x.minx},{x.maxy},{x.maxx}"
                for x in wards["gdf"].bounds.itertuples()
            ]
        )
        .rename(
            columns={
                "AREA_SHORT_CODE": "ward_code",
                "AREA_NAME": "ward_name",
            }
        )
    )
    return wards_formatted


def get_building_query(bbox: str) -> str:
    return f"""[out:xml][timeout:30][bbox:{bbox}];
area["official_name"="City of Toronto"]->.toArea;
(
    nwr["amenity"="toilets"](area.toArea);
    nwr["building"="toilets"](area.toArea);
)->.toWashrooms;
(
    way(around.toWashrooms:50)["building"];
    -
    way.toWashrooms;
)->.nearbyBuildings;
(.nearbyBuildings;>;);
out meta;"""


def get_washrooms_query(bbox: str) -> str:
    return f"""[out:xml][timeout:30][bbox:{bbox}];
area["official_name"="City of Toronto"]->.toArea;
(
  nwr["amenity"="toilets"](area.toArea);
  nwr["building"="toilets"](area.toArea);
);
(._;>;); 
out meta;"""


if __name__ == "__main__":
    generate_imports()

import json
import os
import re
from typing import Literal

import geopandas as gpd
import pandas as pd
import pandera as pa

from resources.openstreetmap import (
    query_overpass,
    feature_from_element,
)
from resources.torontoopendata import request_tod_gdf, TODResponse
from resources.toronto_encoding_issues import encoding_fixes, spelling_fixes

PROPOSAL_WIKI_LINK = (
    "https://wiki.openstreetmap.org/wiki/Import/Toronto_Public_Washroom_Import"
)


def generate_imports():
    """Main script function to get, transform, and save data"""

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

    pfr_washrooms_corrected = (
        pfr_washrooms["gdf"]
        .replace(encoding_fixes, regex=True)
        .replace(spelling_fixes, regex=True)
    )

    # merge facility info into city washrooms dataset
    pfr_washrooms_type = pd.merge(
        pfr_washrooms_corrected,
        pfr_facility_types.rename(
            columns={"LOCATIONID": "parent_id", "TYPE": "parent_type"}
        ),
        how="left",
        on="parent_id",
    )

    # normalize city washroom data into osm tags
    pfr_washrooms_osm = get_pfr_washrooms_osm_open(pfr_washrooms_type)
    pfr_washrooms_osm_status0 = get_pfr_washrooms_osm_closed_or_alert(
        pfr_washrooms_type, status="0"
    )
    pfr_washrooms_osm_status2 = get_pfr_washrooms_osm_closed_or_alert(
        pfr_washrooms_type, status="2"
    )

    # organize status 1 washrooms into ward-level changesets
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
            f"to_import/by_ward/{ward_full}/{ward_full}_toilets_query.txt", "w"
        ) as f:
            f.write(get_washrooms_query(ward_gdf["ward_bbox"].iloc[0]))
        with open(
            f"to_import/by_ward/{ward_full}/{ward_full}_changeset_tags.txt", "w"
        ) as f:
            f.write(
                get_changeset_tags(
                    subset_name=ward_full,
                    source_date=pfr_washrooms["metadata"]["last_modified"][0:10],
                    wiki_link=PROPOSAL_WIKI_LINK,
                )
            )

    # filter and organize status 0 washrooms into winter hours changesets
    # logic only valid if run during winter season
    ccbs = get_community_council_boundaries_gdf()
    washrooms_winter_closed = pfr_washrooms_osm_status0[
        pfr_washrooms_osm_status0["DELETE_Status_Reason"].str.contains(
            "closed for the season", case=False
        )
    ].assign(
        opening_hours=pfr_washrooms_osm_status0["opening_hours"].str.replace(
            "May-Oct 09:00-22:00", "May-Oct 09:00-22:00; Nov-Apr off"
        ),
        note=pfr_washrooms_osm_status0["note"].str.replace(
            "Please survey to determine: Is this washroom open in the winter? opening_hours if yes are likely May-Oct 09:00-22:00; Nov-Apr 09:00-20:00, if no likely May-Oct 09:00-22:00; Nov-Apr off",
            "",
        ),
    )
    # no current reliable way to determine washrooms_winter_open
    washrooms_winter = pd.concat([washrooms_winter_closed])
    washrooms_winter_ccbs = washrooms_winter.sjoin(ccbs, how="left").drop(
        columns=["index_right"]
    )
    washrooms_winter_by_ccb = {
        k: v for k, v in washrooms_winter_ccbs.groupby("ccb_name")
    }

    # save files to use in JOSM import
    for ccb_name, ccb_gdf in washrooms_winter_by_ccb.items():
        os.makedirs(f"to_import/winter_hours/{ccb_name}/", exist_ok=True)
        with open(
            f"to_import/winter_hours/{ccb_name}/{ccb_name}_washrooms_winter.geojson",
            "w",
        ) as f:
            f.write(
                ccb_gdf.drop(columns=["ccb_name", "ccb_bbox"]).to_json(
                    na="drop",
                    drop_id=True,
                    indent=2,
                )
            )
        with open(
            f"to_import/winter_hours/{ccb_name}/{ccb_name}_toilets_query.txt", "w"
        ) as f:
            f.write(get_washrooms_query(ccb_gdf["ccb_bbox"].iloc[0]))
        with open(
            f"to_import/winter_hours/{ccb_name}/{ccb_name}_changeset_tags.txt", "w"
        ) as f:
            f.write(
                get_changeset_tags(
                    subset_name=f"{ccb_name} (Winter Hours)",
                    source_date=pfr_washrooms["metadata"]["last_modified"][0:10],
                    wiki_link=PROPOSAL_WIKI_LINK,
                )
            )

    # generate summary statistics
    changesets = pd.DataFrame(
        {
            "ward_full": [k for k in pfr_by_ward.keys()],
            "size": [len(v) for v in pfr_by_ward.values()],
        }
    )
    changesets_winter = pd.DataFrame(
        {
            "ccb_name": [k for k in washrooms_winter_by_ccb.keys()],
            "size": [len(v) for v in washrooms_winter_by_ccb.values()],
        }
    )
    summary = []
    summary.append("\n===== SUMMARY =====\n")
    summary.append(
        f"{len(pfr_washrooms['gdf'])} data points in original Park Washroom Facilities dataset"
    )
    summary.append(f"{len(pfr_washrooms_osm)} data points in normalized import dataset")
    summary.append(
        f"{len(pfr_washrooms_osm_status0)} data points with Status 0 (closed)"
    )
    summary.append(
        f"{len(washrooms_winter)} data points in winter hours import dataset; {len(washrooms_winter_closed)} closed"
    )
    summary.append(
        f"{len(pfr_washrooms_osm_status2)} data points with Status 2 (service alert)"
    )
    summary.append("")
    summary.append(
        f"{len(changesets)} changesets generated, largest has {changesets['size'].max()} points, and smallest has {changesets['size'].min()} points"
    )
    summary.append(changesets.to_string(index=False))
    summary.append("")
    summary.append(
        f"{len(changesets_winter)} winter hours changesets generated, largest has {changesets_winter['size'].max()} points, and smallest has {changesets_winter['size'].min()} points"
    )
    summary.append(changesets_winter.to_string(index=False))
    print("\n".join(summary))


def get_current_washrooms():
    """Retrieves amenity=toilets that are currently in OpenStreetMap within the City of Toronto. Saves output to source_data/current_washrooms.json"""

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
    """Converts the output from get_current_washrooms into a GeoDataFrame. Saves output to source_data/current_washrooms.geojson"""
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
    """Retrieves, validates, and saves data from the Park Washroom Facilities dataset on open.toronto.ca. Saves gdf output to source_data/pfr_washrooms.geojson and metadata output to source_data/pfr_washrooms_meta.json"""

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
            "address": pa.Column(str, nullable=True),
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
    with open("source_data/pfr_washrooms_meta.json", "w") as f:
        json.dump(pfr_washrooms["metadata"], f, indent=2)
    return pfr_washrooms


def get_pfr_facilities() -> TODResponse:
    """Retrieves, validates, and saves data from the Parks and Recreation Facilities dataset on open.toronto.ca. Saves gdf output to source_data/pfr_facilities.geojson and metadata output to source_data/pfr_facilities_meta.json"""

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
    with open("source_data/pfr_facilities_meta.json", "w") as f:
        json.dump(pfr_facilities["metadata"], f, indent=2)
    return pfr_facilities


def get_pfr_facility_types(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Simplifies and de-duplicates facility type entries returned by get_pfr_facilities"""

    return (
        gdf[["LOCATIONID", "TYPE"]]
        .sort_values("TYPE", ascending=True)
        .groupby("LOCATIONID", as_index=False)
        .agg(lambda x: "|".join(pd.unique(x)))
    )


# functions to normalize city data to openstreetmap tags
def get_access(asset_id):
    """Public access ("yes") with the exception of Jack Layton Ferry Terminal Washroom (asset_id: 58062) where the description indicates it is behind fare paid area."""
    return "customers" if asset_id == 58062 else "yes"


def pattern_search(pattern):
    def f(asset_name):
        match = re.search(pattern, asset_name, re.IGNORECASE)
        return "yes" if match != None else pd.NA

    return f


def get_changing_table(accessible: str):
    return "yes" if "Child Change Table" in accessible else pd.NA


def get_changing_table_adult(accessible: str):
    return "yes" if "Adult Change Table" in accessible else pd.NA


def get_wheelchair(accessible: str):
    if accessible == "None":
        return "no"
    if (
        ("Entrance at Grade" in accessible) or ("Entrance Access Ramp" in accessible)
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
    return f"Accessible features: {', '.join([x for x in features if x is not None])}"


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
    if row["hours"] == "9 a.m. to 10 p.m." and row["parent_type"] == "Park":
        prompts.append(
            "Is this washroom open in the winter? opening_hours if yes are likely May-Oct 09:00-22:00; Nov-Apr 09:00-20:00, if no likely May-Oct 09:00-22:00; Nov-Apr off"
        )
    if (
        row["hours"] == "9 a.m. to 10 p.m."
        and row["parent_type"] == "Community Centre|Park"
    ):
        prompts.append("opening_hours")
    prompt_string = "; ".join(prompts)
    if len(prompt_string) > 0:
        return f"Please survey to determine: {prompt_string}"
    else:
        return pd.NA


def get_pfr_washrooms_osm_open(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Transforms output from get_pfr_washrooms into OpenStreetMap tags for washrooms with status 1 (open). Requires that a "parent_type" column be joined onto the get_pfr_washrooms output to indicate whether the washroom is in a park or a community centre. Saves output to to_import/pfr_to_import.geojson"""

    original_cols = gdf.columns.drop("geometry")

    # filter city data and confirm that (a) filtered data does not contain Reason or Comments columns and (b) that the input data contains an appropriate "parent_type" column
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
            "parent_type": pa.Column(
                str,
                required=True,
                nullable=True,
                checks=pa.Check.isin(
                    ["Park", "Community Centre", "Community Centre|Park"]
                ),
            ),
        }
    )
    schema.validate(gdf_filtered, lazy=True)

    gdf_normalized = (
        gdf_filtered.assign(
            **{
                "amenity": "toilets",
                "access": gdf_filtered["asset_id"].apply(get_access),
                "fee": "no",
                "male": gdf_filtered["AssetName"].apply(
                    pattern_search(r"\bmen's\b|\bmale\b")
                ),
                "female": gdf_filtered["AssetName"].apply(
                    pattern_search(r"\bwomen's\b|\bfemale\b")
                ),
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
                "description": gdf_filtered["location_details"].str.strip(),
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

    # ensure variable length tag values do not exceed 255 char limit
    output_schema = pa.DataFrameSchema(
        {
            "wheelchair:description": pa.Column(
                str,
                nullable=True,
                checks=pa.Check.str_length(max_value=255),
            ),
            "description": pa.Column(
                str,
                nullable=True,
                checks=pa.Check.str_length(max_value=255),
            ),
            "note": pa.Column(
                str,
                nullable=True,
                checks=pa.Check.str_length(max_value=255),
            ),
        }
    )
    output_schema.validate(gdf_normalized)

    with open("to_import/pfr_to_import.geojson", "w") as f:
        f.write(
            gdf_normalized.to_json(
                na="drop",
                drop_id=True,
                indent=2,
            )
        )
    return gdf_normalized


def get_pfr_washrooms_osm_closed_or_alert(
    gdf: gpd.GeoDataFrame, status: Literal["0", "2"]
) -> gpd.GeoDataFrame:
    """Transforms output from get_pfr_washrooms into OpenStreetMap tags for washrooms with status 0 (closed) or status 2 (service alert). Requires that a "parent_type" column be joined onto the get_pfr_washrooms output to indicate whether the washroom is in a park or a community centre. Saves output to to_import/pfr_status_<#>_to_review.geojson"""

    original_cols = gdf.columns.drop("geometry")

    # filter city data and confirm that the input data contains an appropriate "parent_type" column
    gdf_filtered = gdf[(gdf["type"] == "Washroom Building") & (gdf["Status"] == status)]
    schema = pa.DataFrameSchema(
        {
            "parent_type": pa.Column(
                str,
                required=True,
                nullable=True,
                checks=pa.Check.isin(
                    ["Park", "Community Centre", "Community Centre|Park"]
                ),
            ),
        }
    )
    schema.validate(gdf_filtered, lazy=True)

    gdf_normalized = (
        gdf_filtered.assign(
            **{
                "DELETE_Status_PostedDate": gdf_filtered["PostedDate"].dt.strftime(
                    "%Y-%m-%dT%H:%M:%S.%f%z"
                ),
                "DELETE_Status_Reason": gdf_filtered["Reason"],
                "DELETE_Status_Comments": gdf_filtered["Comments"],
                "amenity": "toilets",
                "access": gdf_filtered["asset_id"].apply(get_access),
                "fee": "no",
                "male": gdf_filtered["AssetName"].apply(
                    pattern_search(r"\bmen's\b|\bmale\b")
                ),
                "female": gdf_filtered["AssetName"].apply(
                    pattern_search(r"\bwomen's\b|\bfemale\b")
                ),
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
                "description": gdf_filtered["location_details"].str.strip(),
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

    # ensure variable length tag values do not exceed 255 char limit
    output_schema = pa.DataFrameSchema(
        {
            "wheelchair:description": pa.Column(
                str,
                nullable=True,
                checks=pa.Check.str_length(max_value=255),
            ),
            "description": pa.Column(
                str,
                nullable=True,
                checks=pa.Check.str_length(max_value=255),
            ),
            "note": pa.Column(
                str,
                nullable=True,
                checks=pa.Check.str_length(max_value=255),
            ),
        }
    )
    output_schema.validate(gdf_normalized)

    with open(f"to_import/pfr_status_{status}_to_review.geojson", "w") as f:
        f.write(
            gdf_normalized.to_json(
                na="drop",
                drop_id=True,
                indent=2,
            )
        )
    return gdf_normalized


def get_wards_gdf() -> gpd.GeoDataFrame:
    """Retrieves, simplifies, and saves data from the City Wards dataset from open.toronto.ca"""

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


def get_community_council_boundaries_gdf() -> gpd.GeoDataFrame:
    """Retrieves, simplifies, and saves data from the Community Council Boundaries dataset from open.toronto.ca"""

    ccbs = request_tod_gdf(
        dataset_name="community-council-boundaries",
        resource_id="cc935c56-dbcd-4035-b156-a7f8f8eae68b",
    )
    ccbs_formatted = (
        ccbs["gdf"][["AREA_NAME", "geometry"]]
        .assign(
            ccb_name=ccbs["gdf"]["AREA_NAME"]
            .str.removesuffix("Community Council")
            .str.strip(),
            ccb_bbox=[
                f"{x.miny},{x.minx},{x.maxy},{x.maxx}"
                for x in ccbs["gdf"].bounds.itertuples()
            ],
        )
        .drop(columns=["AREA_NAME"])
    )
    return ccbs_formatted


def get_washrooms_query(bbox: str) -> str:
    """Generates a query to retrieve amenity=toilets that are currently in OpenStreetMap within a custom bounding box"""

    return f"""[out:xml][timeout:30][bbox:{bbox}];
area["official_name"="City of Toronto"]->.toArea;
(
  nwr["amenity"="toilets"](area.toArea);
  nwr["building"="toilets"](area.toArea);
);
(._;>;); 
out meta;"""


def get_changeset_tags(
    subset_name: str,
    source_date: str,
    wiki_link: str,
) -> str:
    """Generates changeset tags to use in JOSM"""

    tags = {
        "comment": f"Toronto Public Washroom Import, subset {subset_name}",
        "import": "yes",
        "source": "City of Toronto",
        "source:url": "https://open.toronto.ca/dataset/washroom-facilities/",
        "source:date": source_date,
        "import:page": wiki_link,
        "source:license": "Open Government License - Toronto",
    }
    return "\n".join([k + "\t" + v for k, v in tags.items()])


if __name__ == "__main__":
    generate_imports()

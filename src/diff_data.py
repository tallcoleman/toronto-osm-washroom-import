from argparse import ArgumentParser
from pathlib import Path

import geopandas as gpd
import pandas as pd


def parse_gdf(input: str):
    if input is None:
        return None
    # test filename is real?
    # test is real GeoJSON?
    gdf = gpd.read_file(input)
    return gdf


# add typing
def get_files_to_compare() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    parser = ArgumentParser()
    parser.add_argument(
        "file_one", type=parse_gdf, help="Earlier file in GeoJSON format"
    )
    parser.add_argument(
        "file_two", type=parse_gdf, help="Later file in GeoJSON format"
    )
    args = parser.parse_args()
    return (args.file_one, args.file_two)


def print_rows(gdf: gpd.GeoDataFrame):
    for index, values in gdf.iterrows():
        print("\n", index, values, sep="\n")


def compare_files():
    file_one, file_two = get_files_to_compare()
    file_one = (file_one.rename(columns={
        "ref:open.toronto.ca:washroom-facilities:asset_id": "asset_id"}).set_index("asset_id"))
    file_two = (file_two.rename(columns={
        "ref:open.toronto.ca:washroom-facilities:asset_id": "asset_id"}).set_index("asset_id"))
    inter_index = file_one.index.intersection(file_two.index)
    inter_cols = file_one.columns.intersection(file_two.columns)
    comparison_one = file_one.loc[inter_index][inter_cols].sort_index()
    comparison_two = file_two.loc[inter_index][inter_cols].sort_index()
    comparison = comparison_one.compare(comparison_two, align_axis="index")
    removed = file_one[~file_one.index.isin(file_two.index)]
    added = file_two[~file_two.index.isin(file_one.index)]

    print("\n\n===CHANGED VALUES===")
    print("asset_id: ", comparison.index.values)
    print_rows(comparison)
    print("\n\n===REMOVED VALUES===")
    print("asset_id: ", removed.index.values)
    print_rows(removed)
    print("\n\n===ADDED VALUES===")
    print("asset_id: ", added.index.values)
    print_rows(added)


if __name__ == "__main__":
    compare_files()

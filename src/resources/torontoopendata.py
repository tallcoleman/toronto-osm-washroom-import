import requests
from typing import TypedDict

import geopandas as gpd
import pandas as pd


BASE_URL = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
PACKAGE_URL = BASE_URL + "/api/3/action/package_show"


class TODResponse(TypedDict):
    gdf: gpd.GeoDataFrame
    metadata: dict


def request_tod_gdf(dataset_name: str, resource_id: str) -> TODResponse:
    meta_params = {"id": dataset_name}
    meta_all = requests.get(PACKAGE_URL, params=meta_params).json()
    [meta_resource] = [
        rs for rs in meta_all["result"]["resources"] if rs["id"] == resource_id
    ]
    gdf: gpd.GeoDataFrame = (
        gpd.read_file(meta_resource["url"]).replace("None", pd.NA).convert_dtypes()
    )
    return {
        "gdf": gdf,
        "metadata": meta_resource,
    }

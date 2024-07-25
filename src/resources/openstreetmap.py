import requests
from datetime import datetime

API_URL = r"http://overpass-api.de/api/interpreter"
CRS = "EPSG:4326"


def query_overpass(query: str) -> dict:
    response = requests.post(API_URL, data=query)
    data = response.json()
    data["crs"] = {"type": "name", "properties": {"name": CRS}}
    return data


VIEW_URL = r"https://www.openstreetmap.org/"
INCLUDE_META = ["type", "id", "version"]


def feature_from_element(element: dict) -> dict:
    geometry: dict
    if "lon" in element and "lat" in element:
        coords: tuple = (element["lon"], element["lat"])
        geometry = {
            "type": "Point",
            "coordinates": coords,
        }
    elif "center" in element:
        coords: tuple = (element["center"]["lon"], element["center"]["lat"])
        geometry = {
            "type": "Point",
            "coordinates": coords,
        }
    elif "geometry" in element:
        geometry = {
            "type": "Polygon",
            "coordinates": [[[e["lon"], e["lat"]] for e in element["geometry"]]],
        }
    else:
        raise KeyError(
            f"""Unable to find coordinates ("lon", "lat", "center", or "geometry") in element {element["type"] + "/" + str(element["id"])}"""
        )

    meta_properties = {
        "_" + key: value for (key, value) in element.items() if key in INCLUDE_META
    }
    # convert "Z" suffix to "+00:00"
    timestamp = {
        "_timestamp": datetime.fromisoformat(element["timestamp"]).isoformat(),
    }
    view_url = {"_url_nwr": VIEW_URL + element["type"] + "/" + str(element["id"])}

    return {
        "type": "Feature",
        "properties": {
            **element["tags"],
            **meta_properties,
            **timestamp,
            **view_url,
        },
        "geometry": geometry,
    }

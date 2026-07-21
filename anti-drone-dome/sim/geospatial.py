"""OpenStreetMap cache loading and local ENU projection helpers."""

import json
import math
import os


def _osm_number(value):
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).split()[0])
    except ValueError:
        return 0.0


def geodetic_to_enu(latitude, longitude, origin_latitude, origin_longitude):
    earth_radius_m = 6378137.0
    north = math.radians(latitude - origin_latitude) * earth_radius_m
    east = (
        math.radians(longitude - origin_longitude)
        * earth_radius_m
        * math.cos(math.radians(origin_latitude))
    )
    return east, north


def enu_to_geodetic(east, north, origin_latitude, origin_longitude):
    earth_radius_m = 6378137.0
    latitude = origin_latitude + math.degrees(float(north) / earth_radius_m)
    longitude = origin_longitude + math.degrees(
        float(east)
        / (earth_radius_m * math.cos(math.radians(origin_latitude)))
    )
    return latitude, longitude


def load_osm_features(cache_path, origin, radius_m):
    if not cache_path or not os.path.isfile(cache_path):
        return {"buildings": [], "roads": []}
    with open(cache_path, "r", encoding="utf-8") as handle:
        osm = json.load(handle)

    nodes = {
        item["id"]: (item["lat"], item["lon"])
        for item in osm.get("elements", [])
        if item.get("type") == "node"
    }
    buildings = []
    roads = []
    for item in osm.get("elements", []):
        if item.get("type") != "way":
            continue
        points = []
        for node_id in item.get("nodes", []):
            if node_id not in nodes:
                continue
            lat, lon = nodes[node_id]
            point = geodetic_to_enu(
                lat, lon, origin["latitude"], origin["longitude"]
            )
            if math.hypot(*point) <= radius_m * 1.25:
                points.append(point)
        if len(points) < 2:
            continue
        tags = item.get("tags", {})
        if "building" in tags and len(points) >= 3:
            levels = _osm_number(tags.get("building:levels"))
            height = _osm_number(tags.get("height"))
            buildings.append({
                "points": points,
                "height_m": height if height > 0 else levels * 3.0,
            })
        elif "highway" in tags:
            roads.append(points)
    return {"buildings": buildings, "roads": roads}

"""Download a bounded OpenStreetMap cache for the configured scenario site."""

import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scenarios import get_site_config


def bounding_box(latitude, longitude, radius_m):
    latitude_delta = math.degrees(radius_m / 6378137.0)
    longitude_delta = latitude_delta / math.cos(math.radians(latitude))
    return (
        latitude - latitude_delta,
        longitude - longitude_delta,
        latitude + latitude_delta,
        longitude + longitude_delta,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint", default="https://overpass-api.de/api/interpreter"
    )
    args = parser.parse_args()
    site = get_site_config()
    origin = site["origin"]
    map_config = site["map"]
    south, west, north, east = bounding_box(
        origin["latitude"], origin["longitude"], map_config["radius_m"]
    )
    query = (
        f"[out:json][timeout:60];("
        f"way[building]({south},{west},{north},{east});"
        f"way[highway]({south},{west},{north},{east});"
        ");(._;>;);out body;"
    )
    request = urllib.request.Request(
        args.endpoint,
        data=urllib.parse.urlencode({"data": query}).encode("ascii"),
        headers={"User-Agent": "anti-drone-dome-simulator/1.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.load(response)
    output = map_config["osm_cache"]
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    print(f"Saved {len(payload.get('elements', []))} OSM elements to {output}")


if __name__ == "__main__":
    main()

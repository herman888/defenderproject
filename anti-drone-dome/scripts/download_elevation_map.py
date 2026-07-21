"""Download a bounded Copernicus GLO-90 elevation grid through Open-Meteo."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
import sys
import urllib.parse
import urllib.request

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scenarios import get_site_config
from sim.geospatial import enu_to_geodetic
from sim.terrain import SCHEMA


def _download_elevations(endpoint, coordinates):
    elevations = []
    for offset in range(0, len(coordinates), 100):
        chunk = coordinates[offset:offset + 100]
        query = urllib.parse.urlencode({
            "latitude": ",".join(f"{lat:.7f}" for lat, _ in chunk),
            "longitude": ",".join(f"{lon:.7f}" for _, lon in chunk),
        })
        request = urllib.request.Request(
            f"{endpoint}?{query}",
            headers={"User-Agent": "project-larp-elevation-cache/1.0"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.load(response)
        values = payload.get("elevation")
        if not isinstance(values, list) or len(values) != len(chunk):
            raise ValueError("elevation API returned an unexpected response")
        elevations.extend(float(value) for value in values)
    return elevations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint", default="https://api.open-meteo.com/v1/elevation"
    )
    parser.add_argument(
        "--acknowledge-approved-site",
        action="store_true",
        help="Confirm the configured coordinates are approved for this use",
    )
    args = parser.parse_args()
    if not args.acknowledge_approved_site:
        parser.error("--acknowledge-approved-site is required")

    site = get_site_config()
    origin = site["origin"]
    map_config = site["map"]
    extent = float(map_config.get("elevation_extent_m", 1500.0))
    spacing = float(map_config.get("elevation_spacing_m", 90.0))
    sample_radius = int(math.ceil(extent / spacing))
    axis = np.arange(-sample_radius, sample_radius + 1, dtype=float) * spacing
    coordinates = [
        enu_to_geodetic(
            east, north, origin["latitude"], origin["longitude"]
        )
        for north in axis
        for east in axis
    ]
    absolute = np.asarray(
        _download_elevations(args.endpoint, coordinates), dtype=float
    ).reshape(len(axis), len(axis))
    center_index = sample_radius
    relative = absolute - absolute[center_index, center_index]
    document = {
        "schema": SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "origin": origin,
        "x_min_m": float(axis[0]),
        "y_min_m": float(axis[0]),
        "spacing_m": spacing,
        "elevations_m": relative.tolist(),
        "source": {
            "provider": "Open-Meteo Elevation API",
            "dataset": "Copernicus DEM GLO-90 2021",
            "resolution_m": 90,
            "doi": "10.5270/ESA-c5d3d65",
        },
    }
    output = map_config["elevation_cache"]
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    print(f"Saved {relative.size} elevation samples to {output}")


if __name__ == "__main__":
    main()

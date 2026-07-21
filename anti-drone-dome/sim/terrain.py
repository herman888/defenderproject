"""Versioned local-ENU elevation grids for terrain collision and rendering."""

from __future__ import annotations

import json
import os

import numpy as np


SCHEMA = "aegis.elevation-grid.v1"


class ElevationGrid:
    def __init__(self, path: str, data: dict):
        if data.get("schema") != SCHEMA:
            raise ValueError(f"elevation grid schema must be {SCHEMA}")
        self.path = os.path.abspath(path)
        self.origin = data["origin"]
        self.spacing_m = float(data["spacing_m"])
        self.x_min_m = float(data["x_min_m"])
        self.y_min_m = float(data["y_min_m"])
        self.elevations_m = np.asarray(data["elevations_m"], dtype=float)
        if self.spacing_m <= 0.0:
            raise ValueError("elevation grid spacing_m must be positive")
        if self.elevations_m.ndim != 2:
            raise ValueError("elevation grid elevations_m must be a 2-D array")
        if min(self.elevations_m.shape) < 2:
            raise ValueError("elevation grid must contain at least 2x2 samples")
        if not np.isfinite(self.elevations_m).all():
            raise ValueError("elevation grid contains non-finite values")
        self.source = data.get("source", {})

    @classmethod
    def load(cls, path: str) -> "ElevationGrid":
        with open(os.path.abspath(path), encoding="utf-8") as handle:
            return cls(path, json.load(handle))

    @property
    def x_max_m(self) -> float:
        return self.x_min_m + self.spacing_m * (self.elevations_m.shape[1] - 1)

    @property
    def y_max_m(self) -> float:
        return self.y_min_m + self.spacing_m * (self.elevations_m.shape[0] - 1)

    def contains(self, x: float, y: float) -> bool:
        return (
            self.x_min_m <= x <= self.x_max_m
            and self.y_min_m <= y <= self.y_max_m
        )

    def elevation(self, x: float, y: float) -> float:
        if not self.contains(x, y):
            raise ValueError("requested point is outside the elevation grid")
        fx = (float(x) - self.x_min_m) / self.spacing_m
        fy = (float(y) - self.y_min_m) / self.spacing_m
        ix = min(int(np.floor(fx)), self.elevations_m.shape[1] - 2)
        iy = min(int(np.floor(fy)), self.elevations_m.shape[0] - 2)
        tx = fx - ix
        ty = fy - iy
        lower = (
            self.elevations_m[iy, ix] * (1.0 - tx)
            + self.elevations_m[iy, ix + 1] * tx
        )
        upper = (
            self.elevations_m[iy + 1, ix] * (1.0 - tx)
            + self.elevations_m[iy + 1, ix + 1] * tx
        )
        return float(lower * (1.0 - ty) + upper * ty)


def load_elevation_grid(path: str | None) -> ElevationGrid | None:
    if not path or not os.path.isfile(path):
        return None
    return ElevationGrid.load(path)

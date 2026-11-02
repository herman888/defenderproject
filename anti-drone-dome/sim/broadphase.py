"""Voxel (spatial-hash) broad phase for dense multi-entity contact queries.

Replaces naive O(N·M) nested loops over interceptors × threats with a
uniform grid whose cell size is the contact radius. Only entities that
share a cell or an adjacent cell are tested exactly. In dense scenarios
(saturation attacks, 20×50) this drops the pair tests from thousands to
a few hundred while remaining exact for the given radius.

The grid is rebuilt each step (cheap: one integer key per entity).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable

import numpy as np


class VoxelBroadPhase:
    """Uniform grid spatial hash for radius queries."""

    def __init__(self, cell_size: float):
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.cell_size = float(cell_size)
        self.inv_cell = 1.0 / self.cell_size
        self._grid: dict[tuple[int, int, int], list[tuple[np.ndarray, Any]]] = defaultdict(list)

    def clear(self) -> None:
        self._grid.clear()

    def _key(self, pos: np.ndarray) -> tuple[int, int, int]:
        p = np.asarray(pos, dtype=float)
        return (
            int(np.floor(p[0] * self.inv_cell)),
            int(np.floor(p[1] * self.inv_cell)),
            int(np.floor(p[2] * self.inv_cell)),
        )

    def insert(self, pos: np.ndarray, payload: Any) -> None:
        """Insert an entity. ``pos`` is copied so later mutation is safe."""
        key = self._key(pos)
        self._grid[key].append((np.asarray(pos, dtype=float).copy(), payload))

    def insert_many(self, positions: Iterable[np.ndarray], payloads: Iterable[Any]) -> None:
        for pos, payload in zip(positions, payloads):
            self.insert(pos, payload)

    def query_candidates(self, pos: np.ndarray) -> list[tuple[np.ndarray, Any]]:
        """Return all entities in the 3×3×3 neighbourhood of ``pos``'s cell.

        Exact distance filtering is left to the caller so the broad phase
        stays allocation-light and radius-agnostic within one cell size.
        """
        ix, iy, iz = self._key(pos)
        out: list[tuple[np.ndarray, Any]] = []
        g = self._grid
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    bucket = g.get((ix + dx, iy + dy, iz + dz))
                    if bucket:
                        out.extend(bucket)
        return out

    def find_pairs_within(
        self,
        radius: float,
        on_hit: Callable[[Any, Any, float], None],
    ) -> int:
        """Optional helper: walk all inserted entities and call ``on_hit`` for
        pairs closer than ``radius``. Returns the number of pairs reported.
        Useful when both sides are inserted into the same grid.
        """
        radius2 = float(radius) * float(radius)
        reported = 0
        seen = set()
        for bucket in self._grid.values():
            for i, (pa, a) in enumerate(bucket):
                for pb, b in bucket[i + 1:]:
                    d2 = float(np.dot(pa - pb, pa - pb))
                    if d2 <= radius2:
                        key = (id(a), id(b)) if id(a) < id(b) else (id(b), id(a))
                        if key not in seen:
                            seen.add(key)
                            on_hit(a, b, d2 ** 0.5)
                            reported += 1
        return reported


def resolve_nearest_within(
    queries: list[tuple[np.ndarray, Any]],
    targets: list[tuple[np.ndarray, Any]],
    radius: float,
) -> list[tuple[Any, Any, float] | None]:
    """For each query, return the nearest target within ``radius`` (or None).

    Builds a voxel grid over the targets (cell size = radius) and only
    examines the 27 neighbouring cells. Exact and deterministic given
    insertion order.
    """
    if not queries or not targets or radius <= 0:
        return [None] * len(queries)

    grid = VoxelBroadPhase(cell_size=radius)
    for pos, payload in targets:
        grid.insert(pos, payload)

    radius2 = radius * radius
    results: list[tuple[Any, Any, float] | None] = []
    for qpos, qpayload in queries:
        best_d2 = radius2
        best = None
        for tpos, tpayload in grid.query_candidates(qpos):
            delta = tpos - qpos
            d2 = float(delta @ delta)
            if d2 <= best_d2:
                best_d2 = d2
                best = (qpayload, tpayload, d2 ** 0.5)
        results.append(best)
    return results

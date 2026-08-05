"""Stable, independent seeding for the stochastic parts of a mission.

Three defects motivated this module, all of which quietly broke reproducibility:

* **Order-derived seeds.** The radar was seeded from
  ``list(INTRUDER_TYPES).index(key) * 100 + list(ATTACK_PATTERNS).index(key)``.
  That is a function of *dict insertion order*, so adding one scenario silently
  renumbered every historical seed and invalidated any prior result quoted
  against it.
* **Unseeded streams.** Wind gusts drew from the module-level ``random``, which
  is never seeded, and the rendered camera sensor received no seed at all, so it
  fell back to OS entropy.
* **Shared streams.** Even seeded, drawing every stochastic quantity from one
  generator couples them: enabling the camera would shift the radar's noise
  sequence and change an unrelated result.

``SeedBundle`` fixes all three. Seeds derive from the scenario's *names* through
a stable digest - not from ``hash()``, which is salted per process and would
make runs irreproducible across interpreter restarts - and each consumer gets an
independent child stream via ``SeedSequence.spawn``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

# Order matters and must never be reordered: each consumer's stream is defined
# by its index in this tuple. Append new consumers to the end.
_STREAMS = ("radar", "camera", "wind", "disturbance", "scenario")


def stable_seed(*parts) -> int:
    """Deterministic 63-bit seed from the given identifiers.

    Uses BLAKE2b rather than :func:`hash`, whose string hashing is randomised
    per process unless ``PYTHONHASHSEED`` is fixed. Reordering a dictionary
    elsewhere in the codebase cannot change this value; only the identifiers can.
    """
    digest = hashlib.blake2b(digest_size=8)
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\x1f")  # unambiguous separator
    return int.from_bytes(digest.digest(), "big") & ((1 << 63) - 1)


@dataclass(frozen=True)
class SeedBundle:
    """Independent RNG streams for one mission."""

    seed: int
    _streams: dict

    @classmethod
    def for_mission(cls, *parts, seed: int | None = None) -> "SeedBundle":
        """Build a bundle from scenario identifiers, or an explicit seed."""
        root = stable_seed(*parts) if seed is None else int(seed)
        children = np.random.SeedSequence(root).spawn(len(_STREAMS))
        return cls(
            seed=root,
            _streams={
                name: child for name, child in zip(_STREAMS, children)
            },
        )

    def generator(self, stream: str) -> np.random.Generator:
        """A fresh generator for ``stream``, independent of the others."""
        if stream not in self._streams:
            raise KeyError(
                f"unknown stream {stream!r}; known: {sorted(self._streams)}"
            )
        return np.random.default_rng(self._streams[stream])

    def child_seed(self, stream: str) -> int:
        """An integer seed for ``stream``, for consumers that take an int."""
        if stream not in self._streams:
            raise KeyError(
                f"unknown stream {stream!r}; known: {sorted(self._streams)}"
            )
        return int(self._streams[stream].generate_state(1, dtype=np.uint32)[0])

    def manifest(self) -> dict:
        """Provenance block for the run record."""
        return {
            "schema": "aegis.seed-bundle.v1",
            "root_seed": self.seed,
            "streams": {
                name: self.child_seed(name) for name in _STREAMS
            },
        }

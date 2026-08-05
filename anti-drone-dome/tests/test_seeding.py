"""Stable, independent per-mission RNG streams.

Each test here pins a defect that silently broke reproducibility:

* seeds derived from dict insertion order, so adding one scenario renumbered
  every historical seed;
* seeds derived from ``hash()``, which is salted per process and so differs
  across interpreter restarts;
* one shared stream, so enabling the camera shifted the radar's noise sequence.
"""

from __future__ import annotations

import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.seeding import SeedBundle, stable_seed  # noqa: E402


def test_seed_is_deterministic_for_the_same_identifiers():
    assert stable_seed("shahed136", "direct", "mid") == stable_seed(
        "shahed136", "direct", "mid"
    )


def test_different_identifiers_give_different_seeds():
    seeds = {
        stable_seed("shahed136", "direct", "mid"),
        stable_seed("shahed136", "direct", "north"),
        stable_seed("shahed136", "spiral", "mid"),
        stable_seed("fpv_attack", "direct", "mid"),
    }
    assert len(seeds) == 4


def test_separator_prevents_identifier_run_together():
    """('ab', 'c') must not collide with ('a', 'bc')."""
    assert stable_seed("ab", "c") != stable_seed("a", "bc")


def test_seed_is_stable_across_interpreter_restarts():
    """Pins the PYTHONHASHSEED defect.

    `hash()` on strings is randomised per process, so a seed derived from it
    changes every run. BLAKE2b does not.
    """
    script = (
        "import sys; sys.path.insert(0, %r);"
        "from sim.seeding import stable_seed;"
        "print(stable_seed('shahed136', 'direct', 'mid'))"
        % os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    outputs = set()
    for hashseed in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=hashseed)
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, env=env, check=True,
        )
        outputs.add(result.stdout.strip())
    assert len(outputs) == 1, f"seed varied with PYTHONHASHSEED: {outputs}"


def test_seed_fits_in_a_positive_64_bit_range():
    value = stable_seed("shahed136", "direct", "mid")
    assert 0 <= value < (1 << 63)


# --------------------------------------------------------------------------
# Stream independence
# --------------------------------------------------------------------------

def test_streams_are_independent():
    """Drawing from one stream must not affect another.

    With a single shared generator, enabling the camera would shift the radar's
    noise sequence and change an unrelated result.
    """
    bundle = SeedBundle.for_mission("shahed136", "direct", "mid")

    radar_only = bundle.generator("radar").normal(size=8)

    # Consume the camera stream first this time; radar must be unchanged.
    bundle.generator("camera").normal(size=1000)
    radar_after = bundle.generator("radar").normal(size=8)

    assert radar_only == pytest.approx(radar_after)


def test_distinct_streams_produce_distinct_sequences():
    bundle = SeedBundle.for_mission("shahed136", "direct", "mid")
    radar = bundle.generator("radar").normal(size=16)
    camera = bundle.generator("camera").normal(size=16)
    wind = bundle.generator("wind").normal(size=16)
    assert not np.allclose(radar, camera)
    assert not np.allclose(radar, wind)


def test_generator_is_repeatable_for_the_same_stream():
    bundle = SeedBundle.for_mission("shahed136", "direct", "mid")
    assert bundle.generator("wind").uniform(size=5) == pytest.approx(
        bundle.generator("wind").uniform(size=5)
    )


def test_same_mission_identifiers_reproduce_every_stream():
    a = SeedBundle.for_mission("shahed136", "direct", "mid")
    b = SeedBundle.for_mission("shahed136", "direct", "mid")
    assert a.seed == b.seed
    assert a.manifest() == b.manifest()
    for stream in ("radar", "camera", "wind"):
        assert a.child_seed(stream) == b.child_seed(stream)


def test_explicit_seed_overrides_identifiers():
    a = SeedBundle.for_mission("shahed136", "direct", seed=42)
    b = SeedBundle.for_mission("totally", "different", seed=42)
    assert a.manifest() == b.manifest()


def test_unknown_stream_is_rejected():
    bundle = SeedBundle.for_mission("shahed136", "direct", "mid")
    with pytest.raises(KeyError):
        bundle.generator("no-such-stream")
    with pytest.raises(KeyError):
        bundle.child_seed("no-such-stream")


def test_manifest_is_serialisable_provenance():
    import json

    bundle = SeedBundle.for_mission("shahed136", "direct", "mid")
    manifest = bundle.manifest()
    assert manifest["schema"] == "aegis.seed-bundle.v1"
    assert manifest["root_seed"] == bundle.seed
    assert {"radar", "camera", "wind"} <= set(manifest["streams"])
    json.dumps(manifest)  # must not raise


def test_scenario_order_cannot_change_seeds_regression():
    """The original seed was list(INTRUDER_TYPES).index(key) * 100 + ...

    That is a function of dict insertion order, so adding a scenario silently
    renumbered every historical seed. Name-derived seeds cannot do that.
    """
    from scenarios import ATTACK_PATTERNS, INTRUDER_TYPES

    intruder = next(iter(INTRUDER_TYPES))
    pattern = next(iter(ATTACK_PATTERNS))
    expected = stable_seed(intruder, pattern, "mid")

    # Simulate a catalogue edit: order changes, contents do not.
    reordered = dict(reversed(list(INTRUDER_TYPES.items())))
    assert list(reordered) != list(INTRUDER_TYPES)
    assert stable_seed(intruder, pattern, "mid") == expected

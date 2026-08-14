import json
import math
import os
import socket
import sys

import numpy as np
import pybullet
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.environment import InterceptionEnv
from ml.controllers import APNController
from ml.observation import encode_observation, encode_observation_v2
from ml.scenario_curriculum import sample_scenario
from scenarios import get_environment_for_pattern, get_site_config
from sim.geospatial import geodetic_to_enu, load_osm_features
from sim.terrain import ElevationGrid
from sensors.camera import RenderedCameraSensor
from sensors.fusion import TrackFusion
from sensors.radar import RadarNode
from scenarios import INTRUDER_TYPES
from sim.drone import Drone, LoiteringMunition
from sim.physics import PhysicsWorld
from sim.airframe_profiles import (
    get_airframe_profile,
    load_airframe_catalog,
    validate_airframe_profile,
)
from integration.tactical_stream import (
    TacticalSequenceTracker,
    TacticalUdpPublisher,
    UdpEndpoint,
    iter_tactical_recording,
    replay_tactical_recording,
)
from main import _coalesce_dashboard_messages
from dome.killzone import DomeKillZone
from guidance.intercept import PurePursuitGuidance
from guidance.setpoint import GuidanceSetpoint
from viz.sim_control import SimControl, _altitude_time_window
from scripts.benchmark_controllers import paired_comparison, summarize
from scripts.validate_unreal_motion_recording import (
    motion_is_valid,
    summarize_motion,
)


def test_scenario_site_and_environment_are_externalized():
    site = get_site_config()
    environment = get_environment_for_pattern("nap_earth")
    assert site["origin"]["latitude"] == 43.0
    assert environment["wind_gust_mps"] > 0
    assert environment["radar_dwell_steps"] == 4


def test_airframe_profiles_separate_physics_visuals_and_evidence():
    catalog = load_airframe_catalog()
    assert len(catalog) == 4
    shahed = get_airframe_profile("intruder.shahed136.representative-v1")
    assert shahed["rigid_body"]["mass_kg"] == 200.0
    assert shahed["geometry"]["wingspan_m"] == 2.5
    assert shahed["geometry"]["visual_scale"] == 1.0
    assert shahed["evidence"]["status"] == "representative-unvalidated"
    assert shahed["dynamics_model"] == "fidelity_v1"
    shahed["propulsion"]["vertical_force_min_n"] = 3000.0
    with pytest.raises(ValueError, match="cannot exceed"):
        validate_airframe_profile(shahed)


def test_profile_driven_shahed_syncs_pybullet_mass_and_reports_energy():
    client = pybullet.connect(pybullet.DIRECT)
    try:
        intruder = LoiteringMunition(
            "shahed",
            (0.0, 30.0, 12.0),
            client,
            intruder_cfg=INTRUDER_TYPES["shahed136"],
        )
        mass = pybullet.getDynamicsInfo(
            intruder.body_id, -1, physicsClientId=client
        )[0]
        assert mass == pytest.approx(200.0)
        before = intruder.get_state()["energy_remaining_fraction"]
        intruder.set_target(100.0, 30.0, 12.0)
        for _ in range(20):
            intruder.update()
            pybullet.stepSimulation(physicsClientId=client)
        state = intruder.get_state()
        assert state["airframe_profile_id"].startswith("intruder.shahed136")
        assert 0.0 < state["energy_remaining_fraction"] <= before
    finally:
        pybullet.disconnect(client)


def test_interceptor_profile_enforces_independent_force_limits():
    client = pybullet.connect(pybullet.DIRECT)
    try:
        interceptor = Drone(
            "interceptor",
            (0.0, 0.0, 5.0),
            client,
            airframe_profile_id="interceptor.reference-v1",
        )
        limited = interceptor._limit_force([1000.0, 0.0, 1000.0])
        assert np.linalg.norm(limited[:2]) == pytest.approx(260.0)
        assert limited[2] == pytest.approx(260.0)
        assert interceptor._limit_force([0.0, 0.0, -1000.0])[2] == -80.0
    finally:
        pybullet.disconnect(client)


def test_adaptive_guidance_responds_to_target_state_and_stays_bounded():
    guidance = PurePursuitGuidance()
    interceptor = {
        "position": (0.0, 0.0, 10.0),
        "velocity": (8.0, 0.0, 0.0),
        "energy_remaining_fraction": 0.9,
    }
    calm_track = {
        "detected": True,
        "position_estimate": (260.0, 20.0, 40.0),
        "velocity": (-8.0, 0.0, 0.0),
        "acceleration": (0.0, 0.0, 0.0),
        "confidence": 0.95,
    }
    calm_setpoint = guidance.compute_guidance(interceptor, calm_track)
    calm_diagnostics = dict(guidance.last_diagnostics)
    maneuver_track = {
        **calm_track,
        "velocity": (-38.0, 24.0, 2.0),
        "acceleration": (0.0, 13.0, 2.0),
    }
    maneuver_setpoint = guidance.compute_guidance(interceptor, maneuver_track)
    maneuver_diagnostics = dict(guidance.last_diagnostics)

    assert calm_setpoint.velocity is not None
    assert maneuver_setpoint.velocity is not None
    assert (
        maneuver_diagnostics["navigation_gain"]
        > calm_diagnostics["navigation_gain"]
    )
    assert (
        maneuver_diagnostics["command_speed_mps"]
        > calm_diagnostics["command_speed_mps"]
    )
    assert np.linalg.norm(maneuver_setpoint.accel) <= 17.0 * 9.81 + 0.1
    assert all(
        np.isfinite(value)
        for value in maneuver_diagnostics.values()
        if isinstance(value, (int, float))
    )


def test_interceptor_attitude_response_is_smooth_banked_and_yaw_aware():
    client = pybullet.connect(pybullet.DIRECT)
    try:
        interceptor = Drone(
            "interceptor",
            (0.0, 0.0, 5.0),
            client,
            airframe_profile_id="interceptor.reference-v1",
        )
        quaternions = [
            interceptor._smooth_flight_attitude(
                (0.75, 0.18, 0.64),
                (35.0, 5.0, 0.0),
                yaw_ned=0.0,
            )
            for _ in range(40)
        ]
        assert all(np.linalg.norm(value) == pytest.approx(1.0) for value in quaternions)
        step_angles = []
        for first, second in zip(quaternions, quaternions[1:]):
            dot = min(1.0, abs(float(np.dot(first, second))))
            step_angles.append(2.0 * math.acos(dot))
        assert max(step_angles) < math.radians(4.0)
        matrix = np.asarray(
            pybullet.getMatrixFromQuaternion(quaternions[-1])
        ).reshape((3, 3))
        body_up = matrix[:, 2]
        tilt = math.degrees(math.acos(np.clip(body_up[2], -1.0, 1.0)))
        assert 5.0 < tilt <= 48.0
        assert matrix[1, 0] > 0.35
    finally:
        pybullet.disconnect(client)


def test_radar_seed_dwell_and_latency_are_reproducible():
    options = {
        "station_pos": (0.0, 0.0, 0.0),
        "max_range": 100.0,
        "noise_std": 0.2,
        "dwell_steps": 2,
        "latency_steps": 1,
        "seed": 42,
    }
    first = RadarNode(**options)
    second = RadarNode(**options)
    first_results = [first.scan((10.0, 0.0, 5.0)) for _ in range(8)]
    second_results = [second.scan((10.0, 0.0, 5.0)) for _ in range(8)]
    assert first_results == second_results
    assert any(item.get("held_for_dwell") for item in first_results)
    assert any(item.get("latency_pending") for item in first_results)
    assert first._tracker is not None
    assert first._tracker.dt == pytest.approx(2.0 / 240.0)


def test_radar_coast_track_cannot_bypass_latency_or_reset():
    radar = RadarNode(
        station_pos=(0.0, 0.0, 0.0),
        max_range=100.0,
        min_vel=0.0,
        latency_steps=1,
        seed=42,
    )
    pending = radar.scan((10.0, 0.0, 5.0))
    assert pending["latency_pending"]
    assert radar.get_last_track() is None
    delivered = radar.scan((10.1, 0.0, 5.0))
    assert delivered["detected"]
    assert radar.get_last_track()["coasted"]
    radar.reset_latency()
    assert radar.get_last_track() is None


def test_geodetic_projection_and_osm_loading(tmp_path):
    east, north = geodetic_to_enu(43.001, -78.999, 43.0, -79.0)
    assert east > 0
    assert north > 0
    cache = tmp_path / "map.json"
    cache.write_text(json.dumps({"elements": [
        {"type": "node", "id": 1, "lat": 43.0, "lon": -79.0},
        {"type": "node", "id": 2, "lat": 43.0001, "lon": -79.0},
        {"type": "node", "id": 3, "lat": 43.0001, "lon": -78.9999},
        {"type": "way", "id": 4, "nodes": [1, 2, 3], "tags": {"building": "yes"}}
    ]}))
    features = load_osm_features(
        str(cache), {"latitude": 43.0, "longitude": -79.0}, 900.0
    )
    assert len(features["buildings"]) == 1


def test_elevation_grid_bilinear_sampling_and_world_integration(tmp_path):
    cache = tmp_path / "elevation.json"
    cache.write_text(json.dumps({
        "schema": "aegis.elevation-grid.v1",
        "origin": {"latitude": 43.0, "longitude": -79.0, "altitude_m": 100.0},
        "x_min_m": -10.0,
        "y_min_m": -10.0,
        "spacing_m": 10.0,
        "elevations_m": [[0.0, 10.0, 20.0], [10.0, 20.0, 30.0], [20.0, 30.0, 40.0]],
        "source": {"dataset": "test-grid"},
    }))
    grid = ElevationGrid.load(str(cache))
    assert grid.elevation(-5.0, -5.0) == pytest.approx(10.0)
    assert grid.elevation(5.0, 5.0) == pytest.approx(30.0)
    world = PhysicsWorld(
        gui=False,
        site_config={
            "origin": {"latitude": 43.0, "longitude": -79.0, "altitude_m": 100.0},
            "map": {"elevation_cache": str(cache), "radius_m": 0.0},
        },
        render_backend="tiny",
    )
    try:
        assert world.terrain_source == "test-grid"
        assert world.elevation_at(-5.0, -5.0) == pytest.approx(10.0)
        assert world.elevation_at(100.0, 100.0) == PhysicsWorld.terrain_elevation(
            100.0, 100.0
        )
        hit = pybullet.rayTest(
            [0.0, 0.0, 100.0],
            [0.0, 0.0, -100.0],
            physicsClientId=world.client,
        )[0]
        assert hit[0] >= 0
        assert hit[3][2] == pytest.approx(20.02, abs=0.25)
    finally:
        pybullet.disconnect(world.client)


def test_training_and_live_observation_shape_matches():
    encoded = encode_observation(
        (0, 0, 5), (0, 0, 0), (100, 100, 50), (-10, -10, 0), 0.5, (1, 2, 0), 0.1
    )
    env = InterceptionEnv(pattern="direct", intruder_type="consumer_quad")
    observation, _ = env.reset(seed=7)
    assert encoded.shape == env.observation_space.shape == observation.shape
    next_observation, reward, terminated, truncated, info = env.step(
        np.zeros(3, dtype=np.float32)
    )
    assert next_observation.shape == (16,)
    assert np.isfinite(reward)
    assert not terminated
    assert not truncated
    assert info["separation_m"] > 0
    assert 0.0 < info["battery_fraction"] <= 1.0


def test_relative_v2_observation_is_translation_invariant():
    base = encode_observation_v2(
        (10, 20, 5), (1, 2, 0), (110, 120, 55), (-10, -8, -1),
        0.8, (2, 1, 0), 0.2, 0.9, 0.1,
    )
    translated = encode_observation_v2(
        (1010, -480, 205), (1, 2, 0), (1110, -380, 255), (-10, -8, -1),
        0.8, (2, 1, 0), 0.2, 0.9, 0.1,
    )
    assert base.shape == translated.shape == (21,)
    assert np.allclose(base, translated)


def test_procedural_curriculum_randomizes_relative_start_geometry():
    easy = sample_scenario(np.random.default_rng(4), 0.0)
    hard = sample_scenario(np.random.default_rng(4), 1.0)
    assert easy.difficulty == 0.0
    assert hard.difficulty == 1.0
    assert np.linalg.norm(hard.interceptor_start[:2]) >= 0.0
    env = InterceptionEnv(
        procedural_scenarios=True,
        curriculum_level=1.0,
        observation_version="v2",
    )
    observation, info = env.reset(seed=22)
    assert observation.shape == (21,)
    assert info["scenario_id"]
    assert info["configured_sensor_latency_s"] >= 0.0


def test_apn_controller_runs_against_training_environment():
    env = InterceptionEnv(pattern="direct", intruder_type="consumer_quad")
    observation, _ = env.reset(seed=8)
    action = APNController().predict(observation, env)
    assert action.shape == (3,)
    assert np.all(action >= -1.0)
    assert np.all(action <= 1.0)


def test_zero_residual_preserves_apn_base_command():
    absolute_env = InterceptionEnv(pattern="direct", intruder_type="consumer_quad")
    residual_env = InterceptionEnv(
        pattern="direct", intruder_type="consumer_quad", residual_apn=True
    )
    absolute_observation, _ = absolute_env.reset(seed=9)
    residual_env.reset(seed=9)
    apn_action = APNController().predict(absolute_observation, absolute_env)
    absolute_env.step(apn_action)
    residual_env.step(np.zeros(3, dtype=np.float32))
    assert np.allclose(
        absolute_env.interceptor_position,
        residual_env.interceptor_position,
        atol=1e-5,
    )


def test_rendered_camera_detects_target_body():
    client = pybullet.connect(pybullet.DIRECT)
    try:
        visual = pybullet.createVisualShape(
            pybullet.GEOM_BOX,
            halfExtents=[2.0, 2.0, 2.0],
            rgbaColor=[1.0, 0.0, 0.0, 1.0],
            physicsClientId=client,
        )
        target = pybullet.createMultiBody(
            0,
            baseVisualShapeIndex=visual,
            basePosition=[0.0, 30.0, 12.0],
            physicsClientId=client,
        )
        sensor = RenderedCameraSensor(
            client,
            position=(0.0, 0.0, 12.0),
            position_noise_std_m=0.0,
            dropout_probability=0.0,
            latency_frames=1,
            exposure_gain=0.9,
            lens_distortion_fraction=0.001,
            rolling_shutter_readout_s=0.01,
        )
        pending = sensor.observe(target, (0.0, 30.0, 12.0), 0.0)
        assert pending["latency_pending"]
        sensor.reset_latency()
        pending = sensor.observe(target, (0.0, 30.0, 12.0), 0.05)
        assert pending["latency_pending"]
        detection = sensor.observe(target, (0.0, 30.0, 12.0), 0.10)
        assert detection["detected"]
        assert detection["pixel_count"] > 0
        assert detection["effects"]["exposure_gain"] == 0.9
        assert np.linalg.norm(
            np.asarray(detection["position_estimate"]) - np.asarray([0.0, 30.0, 12.0])
        ) < 5.0
    finally:
        pybullet.disconnect(client)


def test_command_center_control_state_exposes_runtime_failures():
    control = SimControl()
    assert control.runtime_speed == 1.0
    assert not control.radar_failure
    assert not control.camera_failure
    assert not control.actuator_failure


def test_loitering_munition_exposes_camera_body_id():
    client = pybullet.connect(pybullet.DIRECT)
    try:
        intruder = LoiteringMunition(
            "camera_target",
            (0.0, 30.0, 12.0),
            client,
            intruder_cfg=INTRUDER_TYPES["consumer_quad"],
        )
        assert intruder.body_id >= 0
        assert intruder.body_id == intruder._body
    finally:
        pybullet.disconnect(client)


def test_radar_and_camera_tracks_fuse_into_common_track():
    fusion = TrackFusion()
    fused = fusion.update(
        {
            "detected": True,
            "position_estimate": (100.0, 50.0, 20.0),
            "velocity": (-5.0, 0.0, 0.0),
        },
        {
            "detected": True,
            "position_estimate": (102.0, 48.0, 21.0),
            "velocity": (-4.0, 0.0, 0.0),
            "confidence": 0.8,
        },
        radar_confidence=0.9,
        timestamp=1.0,
    )
    assert fused["source"] == "RADAR+EO"
    assert fused["confidence"] > 0.9
    assert 100.0 < fused["position_estimate"][0] < 102.0


def test_headless_world_renders_integrated_tactical_frame():
    world = PhysicsWorld(gui=False)
    try:
        frame = world.capture_tactical_view(
            intruder_position=(100.0, 100.0, 50.0),
            interceptor_position=(0.0, 0.0, 20.0),
            width=160,
            height=90,
        )
        assert frame.shape == (90, 160, 3)
        assert frame.dtype == np.uint8
        assert float(frame.std()) > 1.0
    finally:
        pybullet.disconnect(world.client)


def test_structural_terrain_is_flat_at_site_and_raised_at_range():
    assert PhysicsWorld.terrain_elevation(0.0, 0.0) == 0.0
    samples = [
        PhysicsWorld.terrain_elevation(900.0, 0.0),
        PhysicsWorld.terrain_elevation(-700.0, 650.0),
        PhysicsWorld.terrain_elevation(600.0, -800.0),
    ]
    assert max(samples) > 5.0
    assert len({round(value, 2) for value in samples}) > 1


def test_dashboard_queue_coalescing_preserves_lifecycle_and_all_events():
    lifecycle, latest = _coalesce_dashboard_messages([
        {"type": "mission_start"},
        {"mission_time": 1.0, "events": ["Radar track acquired"]},
        {"mission_time": 1.1, "events": ["Radar/EO fusion confirmed"]},
        {"mission_time": 1.2, "events": []},
    ])
    assert lifecycle == [{"type": "mission_start"}]
    assert latest["mission_time"] == 1.2
    assert latest["events"] == [
        "Radar track acquired",
        "Radar/EO fusion confirmed",
    ]


def test_predicted_intercept_is_a_future_lead_point():
    guidance = PurePursuitGuidance()
    interceptor = {"position": (0.0, 0.0, 0.0), "velocity": (0.0, 0.0, 0.0)}
    track = {
        "detected": True,
        "position_estimate": (100.0, 0.0, 0.0),
        "velocity": (0.0, 20.0, 0.0),
    }
    predicted = guidance.predicted_intercept_point(interceptor, track)
    assert predicted is not None
    assert predicted[0] == 100.0
    assert predicted[1] > 0.0
    assert not np.allclose(predicted, track["position_estimate"])


def test_killzone_distinguishes_monitoring_tracking_and_breach_after_launch():
    dome = DomeKillZone(radius=200.0, track_hold_updates=2)
    dome.update_status((600.0, 0.0, 100.0), True)
    assert dome.get_status() == "MONITORING"
    dome.update_status((590.0, 0.0, 100.0), False)
    dome.update_status((580.0, 0.0, 100.0), False)
    assert dome.get_status() == "MONITORING"
    dome.update_status((570.0, 0.0, 100.0), False)
    assert dome.get_status() == "CLEAR"
    dome.update_status((350.0, 0.0, 50.0), True)
    assert dome.get_status() == "TRACKING"
    dome.update_status(
        (100.0, 0.0, 20.0),
        True,
        interceptor_position=(150.0, 0.0, 20.0),
        intercept_radius=18.0,
    )
    assert dome.get_status() == "BREACH"


def test_altitude_window_expands_before_becoming_rolling_history():
    assert _altitude_time_window(3.0)[:2] == (0.0, 30.0)
    assert _altitude_time_window(45.0)[:2] == (0.0, 60.0)
    assert _altitude_time_window(90.0)[:2] == (0.0, 120.0)
    assert _altitude_time_window(145.0)[:2] == (25.0, 145.0)


def test_benchmark_reports_uncertainty_and_paired_deltas():
    base_episode = {
        "pattern": None,
        "intruder_type": None,
        "seed": 1,
        "intercepted": True,
        "duration_s": 10.0,
        "minimum_separation_m": 15.0,
        "energy_used": 3.0,
        "reward": 100.0,
        "scenario_id": "scenario-a",
        "mean_controller_action_norm": 0.5,
        "action_saturation_fraction": 0.1,
        "mean_applied_acceleration_mps2": 20.0,
    }
    candidate_episode = {
        **base_episode,
        "duration_s": 9.0,
        "energy_used": 2.5,
        "reward": 105.0,
    }
    summary = summarize("apn", [base_episode])
    comparison = paired_comparison(
        "apn", [base_episode], "ppo", [candidate_episode]
    )
    assert summary["intercept_rate_wilson_95"][0] < 1.0
    assert comparison["paired_episodes"] == 1
    assert (
        comparison["metric_deltas"]["duration_s"][
            "mean_candidate_minus_reference"
        ]
        == -1.0
    )


def test_tactical_camera_suite_projects_tracks_in_every_view():
    world = PhysicsWorld(gui=False)
    try:
        for mode in ("overview", "shahed", "interceptor", "topdown"):
            capture = world.capture_tactical_view(
                intruder_position=(180.0, 130.0, 110.0),
                interceptor_position=(20.0, 10.0, 40.0),
                intruder_velocity=(-35.0, -25.0, -4.0),
                interceptor_velocity=(40.0, 30.0, 20.0),
                predicted_intercept=(80.0, 70.0, 75.0),
                view_mode=mode,
                width=160,
                height=90,
                include_metadata=True,
            )
            assert capture["frame"].shape == (90, 160, 3)
            assert capture["view_mode"] == mode
            assert capture["screen_points"]["intruder"] is not None
    finally:
        pybullet.disconnect(world.client)


def test_shahed_uses_dedicated_fixed_wing_airframe():
    client = pybullet.connect(pybullet.DIRECT)
    try:
        intruder = LoiteringMunition(
            "shahed",
            (0.0, 30.0, 12.0),
            client,
            intruder_cfg=INTRUDER_TYPES["shahed136"],
        )
        assert pybullet.getNumJoints(intruder.body_id, physicsClientId=client) >= 5
    finally:
        pybullet.disconnect(client)


def _tactical_state(mission_time_s=1.25):
    return {
        "mission_time_s": mission_time_s,
        "timestamp_clock": "simulation-relative",
        "status": "TRACKING",
        "site": "Synthetic renderer test site",
        "guidance": "apn",
        "coordinate_frame": {
            "type": "local-tangent-plane",
            "axes": "ENU",
            "position_unit": "m",
            "velocity_unit": "m/s",
            "orientation": "xyzw",
        },
        "georeference": {
            "origin": {
                "latitude": 43.0,
                "longitude": -79.0,
                "altitude_m": 0.0,
            },
            "status": "placeholder",
        },
        "terrain": {
            "source": "PROCEDURAL TEST",
            "collision_authoritative": True,
        },
        "tracks": {
            "intruder": {
                "id": "TRK-001",
                "role": "intruder",
                "asset_id": "intruder/shahed136",
                "type": "shahed136",
                "position_enu_m": [100.0, 200.0, 50.0],
                "velocity_enu_mps": [-10.0, 0.0, 0.0],
                "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
            },
            "interceptor": None,
        },
    }


def test_versioned_udp_tactical_stream_round_trip_and_recording(tmp_path):
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(1.0)
    host, port = receiver.getsockname()
    recording = tmp_path / "tactical.jsonl"
    publisher = TacticalUdpPublisher(
        UdpEndpoint(host, port),
        recording_path=recording,
    )
    try:
        published = publisher.publish(_tactical_state())
        payload, _ = receiver.recvfrom(65535)
        packet = json.loads(payload)
        assert packet["schema"] == "aegis.tactical.v1"
        assert packet["sequence"] == 0
        assert packet["tracks"]["intruder"]["id"] == "TRK-001"
        assert packet["coordinate_frame"]["axes"] == "ENU"
        assert packet["georeference"]["status"] == "placeholder"
        assert packet["tracks"]["intruder"]["orientation_xyzw"][-1] == 1.0
        assert published == packet
    finally:
        publisher.close()
        receiver.close()
    assert list(iter_tactical_recording(recording)) == [packet]


def test_tactical_recording_preserves_existing_evidence(tmp_path):
    recording = tmp_path / "existing.jsonl"
    recording.write_text("existing evidence\n", encoding="utf-8")
    publisher = TacticalUdpPublisher(
        UdpEndpoint("127.0.0.1", 49000),
        recording_path=recording,
    )
    try:
        assert publisher.recording_path == tmp_path / "existing.001.jsonl"
    finally:
        publisher.close()
    assert recording.read_text(encoding="utf-8") == "existing evidence\n"
    assert (tmp_path / "existing.001.jsonl").exists()


def test_tactical_motion_validator_requires_both_tracks_to_move(tmp_path):
    recording = tmp_path / "motion.jsonl"
    packets = []
    for sequence in range(4):
        packets.append({
            "status": "TRACKING",
            "simulation": {"guidance_mode": "ADAPTIVE_APN"},
            "tracks": {
                "intruder": {
                    "position_enu_m": [100.0 - sequence, 0.0, 20.0],
                },
                "interceptor": (
                    None
                    if sequence == 0
                    else {"position_enu_m": [float(sequence), 0.0, 10.0]}
                ),
            },
        })
    recording.write_text(
        "\n".join(json.dumps(packet) for packet in packets) + "\n",
        encoding="utf-8",
    )
    summary = summarize_motion(recording)
    assert summary["both_moving_intervals"] == 2
    assert motion_is_valid(summary)

    packets[-1]["tracks"]["interceptor"]["position_enu_m"] = [2.0, 0.0, 10.0]
    recording.write_text(
        "\n".join(json.dumps(packet) for packet in packets) + "\n",
        encoding="utf-8",
    )
    assert not motion_is_valid(summarize_motion(recording))


def test_tactical_sequence_tracking_and_exact_udp_replay(tmp_path):
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(1.0)
    host, port = receiver.getsockname()
    recording = tmp_path / "tactical.jsonl"
    packet = {"schema": "aegis.tactical.v1", "sequence": 0, **_tactical_state()}
    recording.write_text(json.dumps(packet) + "\n", encoding="utf-8")

    tracker = TacticalSequenceTracker()
    assert tracker.accept(packet) == 0
    with pytest.raises(ValueError, match="stale tactical sequence"):
        tracker.accept(packet)
    skipped = json.loads(json.dumps(packet))
    skipped["sequence"] = 2
    skipped["mission_time_s"] = 2.0
    assert tracker.accept(skipped) == 1

    try:
        assert replay_tactical_recording(
            recording,
            UdpEndpoint(host, port),
            wait=False,
        ) == 1
        payload, _ = receiver.recvfrom(65535)
        assert json.loads(payload) == packet
    finally:
        receiver.close()

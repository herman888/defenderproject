import json
import os
import socket
import sys

import numpy as np
import pybullet

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.environment import InterceptionEnv
from ml.controllers import APNController
from ml.observation import encode_observation, encode_observation_v2
from ml.scenario_curriculum import sample_scenario
from scenarios import get_environment_for_pattern, get_site_config
from sim.geospatial import geodetic_to_enu, load_osm_features
from sensors.camera import RenderedCameraSensor
from sensors.fusion import TrackFusion
from scenarios import INTRUDER_TYPES
from sim.drone import LoiteringMunition
from sim.physics import PhysicsWorld
from integration.tactical_stream import TacticalUdpPublisher, UdpEndpoint
from main import _coalesce_dashboard_messages
from dome.killzone import DomeKillZone
from guidance.intercept import PurePursuitGuidance
from viz.dashboard import _altitude_time_window
from scripts.benchmark_controllers import paired_comparison, summarize


def test_scenario_site_and_environment_are_externalized():
    site = get_site_config()
    environment = get_environment_for_pattern("nap_earth")
    assert site["origin"]["latitude"] == 43.0
    assert environment["wind_gust_mps"] > 0


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
        )
        detection = sensor.observe(target, (0.0, 30.0, 12.0), 0.0)
        assert detection["detected"]
        assert detection["pixel_count"] > 0
        assert np.linalg.norm(
            np.asarray(detection["position_estimate"]) - np.asarray([0.0, 30.0, 12.0])
        ) < 5.0
    finally:
        pybullet.disconnect(client)


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


def test_versioned_udp_tactical_stream_round_trip():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(1.0)
    host, port = receiver.getsockname()
    publisher = TacticalUdpPublisher(UdpEndpoint(host, port))
    try:
        publisher.publish({
            "mission_time_s": 1.25,
            "status": "TRACKING",
            "tracks": {"intruder": {"id": "TRK-001"}},
        })
        payload, _ = receiver.recvfrom(65535)
        packet = json.loads(payload)
        assert packet["schema"] == "aegis.tactical.v1"
        assert packet["sequence"] == 0
        assert packet["tracks"]["intruder"]["id"] == "TRK-001"
    finally:
        publisher.close()
        receiver.close()

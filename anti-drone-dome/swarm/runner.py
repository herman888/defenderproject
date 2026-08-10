"""Headless point-mass swarm engagement runner + CLI.

Simulates a saturation attack against a coordinated interceptor swarm using the same
point-mass dynamics family as ``ml/environment.py`` and the real APN guidance from
``guidance/intercept.py``. The coordination brain (``swarm/coordinator.py``) is shared
verbatim with the PyBullet path. Deterministic given the scenario seed.

Run directly:
    python swarm/runner.py --scenario saturation_6v4 --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from guidance.intercept import PurePursuitGuidance  # noqa: E402
from guidance.setpoint import ned_to_enu  # noqa: E402
from scenarios import INTRUDER_TYPES  # noqa: E402
from sim.airframe_profiles import get_airframe_profile  # noqa: E402
from sim.flight_envelope import FlightEnvelope, limit_acceleration  # noqa: E402
from sim.seeding import SeedBundle  # noqa: E402
from sensors.radar_batch import MultiTargetRadar  # noqa: E402
from swarm.coordinator import SwarmCoordinator  # noqa: E402
from swarm.rf_link import RfLinkModel  # noqa: E402
from swarm.scenario import SwarmScenario, get_swarm_scenario  # noqa: E402
from swarm.telemetry import SwarmTelemetryPublisher, build_swarm_packet  # noqa: E402

_DT = 0.05
_INTERCEPTOR_ENDURANCE_S = 180.0   # full-power flight seconds to empty


def _profile_envelope(profile_id) -> FlightEnvelope:
    if not profile_id:
        return FlightEnvelope()
    try:
        return FlightEnvelope.from_profile(get_airframe_profile(profile_id))
    except (KeyError, ValueError):
        return FlightEnvelope()


def _threat_envelope(threat_type) -> FlightEnvelope:
    cfg = INTRUDER_TYPES.get(threat_type, {})
    return _profile_envelope(cfg.get("airframe_profile_id"))


class _Interceptor:
    def __init__(self, spec):
        self.id = spec.id
        self.position = np.asarray(spec.start_enu_m, dtype=float)
        self.velocity = np.zeros(3, dtype=float)
        self.applied_accel = np.zeros(3, dtype=float)
        self.max_speed = float(spec.max_speed_mps)
        self.actuator_tau = 0.06
        self.envelope = _profile_envelope(spec.airframe_profile_id)
        self.energy = 1.0
        self.expended = False
        self.kill: str | None = None

    def state_dict(self) -> dict:
        return {
            "id": self.id,
            "position": self.position.tolist(),
            "velocity": self.velocity.tolist(),
            "energy_remaining_fraction": self.energy,
        }


class _Threat:
    def __init__(self, spec, protected_center):
        self.id = spec.id
        self.type = spec.type
        self.threat_level = spec.threat_level
        self.position = np.asarray(spec.start_enu_m, dtype=float)
        self.velocity = np.zeros(3, dtype=float)
        self.max_speed = float(spec.max_speed_mps)
        self.envelope = _threat_envelope(spec.type)
        waypoints = list(spec.waypoints_enu_m) or [tuple(protected_center)]
        self.waypoints = [np.asarray(wp, dtype=float) for wp in waypoints]
        self.waypoint_index = 0
        self.status = "ACTIVE"
        self.resolved_time: float | None = None

    def track_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "threat_level": self.threat_level,
            "position_estimate": self.position.tolist(),
            "velocity": self.velocity.tolist(),
        }


@dataclass
class SwarmRunResult:
    scenario_id: str
    seed: int
    policy: str
    sim_time_s: float
    threats_total: int
    interceptors_total: int
    neutralized: int
    breached: int
    leaked: int
    interceptors_expended: int
    retasking_events: int
    link_health: dict
    threat_outcomes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema": "aegis.swarm-run-report.v1",
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "policy": self.policy,
            "sim_time_s": round(self.sim_time_s, 3),
            "threats_total": self.threats_total,
            "interceptors_total": self.interceptors_total,
            "neutralized": self.neutralized,
            "breached": self.breached,
            "leaked": self.leaked,
            "interceptors_expended": self.interceptors_expended,
            "retasking_events": self.retasking_events,
            "link_health": self.link_health,
            "threat_outcomes": self.threat_outcomes,
        }


def _guide(guidance, interceptor: _Interceptor, target_track: dict) -> np.ndarray:
    """Guide against a sensor track, never the scenario's true threat state."""
    track = {
        "detected": True,
        "position_estimate": target_track["position_estimate"],
        "velocity": target_track.get("velocity", (0.0, 0.0, 0.0)),
    }
    setpoint = guidance.compute_guidance(
        {"position": interceptor.position.tolist(),
         "velocity": interceptor.velocity.tolist()},
        track,
    )
    if setpoint.accel is None:
        return np.zeros(3, dtype=float)
    return np.asarray(ned_to_enu(setpoint.accel), dtype=float)


def run_scenario(
    scenario: SwarmScenario,
    *,
    seed: int | None = None,
    policy: str | None = None,
    telemetry: SwarmTelemetryPublisher | None = None,
    max_time_s: float | None = None,
) -> SwarmRunResult:
    seed = int(scenario.seed if seed is None else seed)
    policy = policy or scenario.coordinator.policy
    center = np.asarray(scenario.protected_center_enu_m, dtype=float)
    guidance = PurePursuitGuidance()

    rf_model = RfLinkModel(scenario.coordinator.rf_link, seed=seed)
    coordinator = SwarmCoordinator(
        rf_model,
        protected_center=tuple(center),
        guidance=guidance,
        policy=policy,
    )
    coord_pos = np.asarray(scenario.coordinator.start_enu_m, dtype=float)
    coord_state = {"position": coord_pos.tolist(), "velocity": [0.0, 0.0, 0.0]}

    interceptors = [_Interceptor(spec) for spec in scenario.interceptors]
    threats = [_Threat(spec, center) for spec in scenario.threats]
    seeds = SeedBundle.for_mission("swarm", scenario.scenario_id, seed=seed)
    # Ground truth below is allowed only inside this sensor model to generate
    # measurements.  The coordinator and guidance path consume its anonymous,
    # noisy tracks, not scenario threat IDs or true state.
    radar = MultiTargetRadar(
        station_pos=(center[0], center[1], center[2] + 3.0),
        max_range=1500.0,
        noise_std=1.5,
        confirmation_hits=3,
        max_misses=10,
        dt=_DT,
        seed=seeds.child_seed("radar"),
    )

    max_time_s = float(max_time_s or scenario.duration_limit_s)
    intercept_r = scenario.intercept_radius_m
    breach_r = scenario.breach_radius_m

    prev_states: dict = {}
    retasking_events = 0
    t = 0.0
    steps = int(round(max_time_s / _DT))

    for _ in range(steps):
        active_threats = [th for th in threats if th.status == "ACTIVE"]
        active_interceptors = [it for it in interceptors if not it.expended]
        if not active_threats or not active_interceptors:
            break

        sensor_tracks = radar.scan([
            {
                "position": threat.position,
                "rcs_m2": INTRUDER_TYPES.get(threat.type, {}).get("rcs", 0.01),
            }
            for threat in active_threats
        ], timestamp_s=t)
        # Classification and priority are deliberately conservative until a
        # real classifier is in the loop.  Propagating scenario type/priority
        # would simply reintroduce truth through metadata.
        for track in sensor_tracks:
            track["type"] = "unclassified"
            track["threat_level"] = "MEDIUM"

        plan = coordinator.plan(
            coord_state,
            [it.state_dict() for it in active_interceptors],
            sensor_tracks,
            t,
        )

        # Count re-tasking (link-state) transitions for evidence.
        for iid, order in plan.orders.items():
            if prev_states.get(iid) not in (None, order.state):
                retasking_events += 1
            prev_states[iid] = order.state

        track_by_id = {track["id"]: track for track in sensor_tracks}
        for interceptor in active_interceptors:
            order = plan.orders.get(interceptor.id)
            target = track_by_id.get(order.assigned_threat_id) if order else None
            if target is not None:
                cmd = _guide(guidance, interceptor, target)
            else:
                cmd = -0.5 * interceptor.velocity  # loiter/brake when unassigned
            cmd = limit_acceleration(
                interceptor.velocity, cmd, interceptor.envelope, _DT
            )
            alpha = min(1.0, _DT / interceptor.actuator_tau)
            interceptor.applied_accel += alpha * (cmd - interceptor.applied_accel)
            interceptor.velocity += interceptor.applied_accel * _DT
            speed = float(np.linalg.norm(interceptor.velocity))
            if speed > interceptor.max_speed:
                interceptor.velocity *= interceptor.max_speed / speed
            interceptor.position += interceptor.velocity * _DT
            accel_frac = min(1.0, float(np.linalg.norm(cmd)) / 166.0)
            interceptor.energy = max(
                0.0,
                interceptor.energy
                - _DT / _INTERCEPTOR_ENDURANCE_S * (0.3 + 0.7 * accel_frac),
            )

        # Advance threats toward the protected asset.
        for threat in active_threats:
            target = threat.waypoints[min(threat.waypoint_index, len(threat.waypoints) - 1)]
            delta = target - threat.position
            distance = float(np.linalg.norm(delta))
            if distance < 8.0 and threat.waypoint_index < len(threat.waypoints) - 1:
                threat.waypoint_index += 1
                target = threat.waypoints[threat.waypoint_index]
                delta = target - threat.position
                distance = float(np.linalg.norm(delta))
            desired = delta / max(distance, 1e-6) * threat.max_speed
            # Bank-to-turn dynamics: reach the desired velocity only as fast as
            # the airframe's turn-g / climb / min-airspeed envelope allows.
            accel_cmd = (desired - threat.velocity) / _DT
            accel_cmd = limit_acceleration(
                threat.velocity, accel_cmd, threat.envelope, _DT
            )
            threat.velocity += accel_cmd * _DT
            speed = float(np.linalg.norm(threat.velocity))
            if speed > threat.max_speed:
                threat.velocity *= threat.max_speed / speed
            threat.position += threat.velocity * _DT

        t += _DT

        # Resolve intercepts (nearest interceptor within radius kills the threat).
        for threat in active_threats:
            if threat.status != "ACTIVE":
                continue
            best, best_d = None, intercept_r
            for interceptor in active_interceptors:
                if interceptor.expended:
                    continue
                d = float(np.linalg.norm(interceptor.position - threat.position))
                if d <= best_d:
                    best_d, best = d, interceptor
            if best is not None:
                threat.status = "NEUTRALIZED"
                threat.resolved_time = t
                best.expended = True
                best.kill = threat.id

        # Resolve breaches.
        for threat in active_threats:
            if threat.status != "ACTIVE":
                continue
            if float(np.linalg.norm(threat.position - center)) <= breach_r:
                threat.status = "BREACHED"
                threat.resolved_time = t

        if telemetry is not None:
            telemetry.publish(_telemetry_body(t, coord_pos, interceptors, threats, plan))

    # Any still-active threat survived to the time limit -> leaker.
    for threat in threats:
        if threat.status == "ACTIVE":
            threat.status = "LEAKER"

    neutralized = sum(1 for th in threats if th.status == "NEUTRALIZED")
    breached = sum(1 for th in threats if th.status == "BREACHED")
    leaked = sum(1 for th in threats if th.status == "LEAKER")
    outcomes = [
        {
            "id": th.id,
            "type": th.type,
            "threat_level": th.threat_level,
            "status": th.status,
            "resolved_time_s": (
                round(th.resolved_time, 3) if th.resolved_time is not None else None
            ),
        }
        for th in threats
    ]
    return SwarmRunResult(
        scenario_id=scenario.scenario_id,
        seed=seed,
        policy=policy,
        sim_time_s=t,
        threats_total=len(threats),
        interceptors_total=len(interceptors),
        neutralized=neutralized,
        breached=breached,
        leaked=leaked,
        interceptors_expended=sum(1 for it in interceptors if it.expended),
        retasking_events=retasking_events,
        link_health=coordinator._link_health(plan.orders) if steps else {},
        threat_outcomes=outcomes,
    )


def _telemetry_body(t, coord_pos, interceptors, threats, plan) -> dict:
    interceptor_rows = []
    for interceptor in interceptors:
        order = plan.orders.get(interceptor.id)
        margin = order.link_margin_db if order else float("-inf")
        if not np.isfinite(margin):
            margin = -999.0   # JSON disallows -inf; use a sentinel floor
        interceptor_rows.append({
            "id": interceptor.id,
            "position_enu_m": interceptor.position.tolist(),
            "velocity_enu_mps": interceptor.velocity.tolist(),
            "assigned_threat_id": order.assigned_threat_id if order else None,
            "state": "EXPENDED" if interceptor.expended else (order.state if order else "RESERVE"),
            "link_margin_db": float(margin),
            "energy_remaining_fraction": interceptor.energy,
        })
    threat_rows = [{
        "id": th.id,
        "type": th.type,
        "threat_level": th.threat_level,
        "position_enu_m": th.position.tolist(),
        "velocity_enu_mps": th.velocity.tolist(),
        "status": th.status,
    } for th in threats]
    return build_swarm_packet(
        mission_time_s=t,
        coordinator={
            "id": "coordinator-01",
            "position_enu_m": coord_pos.tolist(),
            "velocity_enu_mps": [0.0, 0.0, 0.0],
        },
        interceptors=interceptor_rows,
        threats=threat_rows,
        assignment={k: v for k, v in plan.assignment.items()},
        link_health=plan.link_health,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="saturation_6v4", help="Swarm scenario id")
    parser.add_argument("--seed", type=int, default=None, help="Override scenario seed")
    parser.add_argument(
        "--policy", choices=("greedy", "hungarian"), default=None,
        help="Override assignment policy",
    )
    parser.add_argument("--output", default=None, help="Write the JSON report to a path")
    parser.add_argument(
        "--telemetry-udp", default=None,
        help="Stream aegis.swarm-coordination.v1 packets to HOST:PORT",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress the summary print")
    args = parser.parse_args(argv)

    try:
        scenario = get_swarm_scenario(args.scenario)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))

    telemetry = None
    if args.telemetry_udp:
        telemetry = SwarmTelemetryPublisher.from_endpoint(args.telemetry_udp)
    try:
        result = run_scenario(
            scenario, seed=args.seed, policy=args.policy, telemetry=telemetry
        )
    finally:
        if telemetry is not None:
            telemetry.close()

    report = result.to_dict()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
    if not args.quiet:
        print(json.dumps(report, indent=2))
        print(
            f"\n{result.scenario_id}: neutralized {result.neutralized}/"
            f"{result.threats_total}, breached {result.breached}, "
            f"leaked {result.leaked}, interceptors used "
            f"{result.interceptors_expended}/{result.interceptors_total}, "
            f"link delivery {result.link_health.get('delivery_ratio', 1.0):.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

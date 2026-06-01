"""Defender scenario: VIPs + defender (left), central building, red-team attack via **PyBullet Params**.

Run::

    python3 gym_pybullet_drones/examples/defender_pid.py --gui true --radar_hud false

In the **PyBullet** window, open the **Params** / user-parameters panel (sliders on the side).
Set **Red ATTACK type** (0 = Rocket, 1 = Swarm, 2 = Dive), then drag **Red FIRE** to **1**
and back toward **0** to launch. Blue drones patrol until then.

**Camera:** click the 3D view, then J/L/I/K/U/O; optional ``--camera_orbit`` / ``--camera_follow``.
"""
from __future__ import annotations

import argparse
import math
import time

import numpy as np
import pybullet as p

from gym_pybullet_drones.utils.enums import DroneModel, Physics
from gym_pybullet_drones.envs.CtrlAviary import CtrlAviary
from gym_pybullet_drones.control.DSLPIDControl import DSLPIDControl
from gym_pybullet_drones.utils.Logger import Logger
from gym_pybullet_drones.utils.utils import sync, str2bool
from gym_pybullet_drones.utils.gui_camera import GuiCameraController
from gym_pybullet_drones.defender import DefenderPolicy, DefenderPolicyConfig
from gym_pybullet_drones.defender.attack_ui import AttackDebugUi
from gym_pybullet_drones.defender.threat_fleet import ThreatFleet
from gym_pybullet_drones.defender.scenario_props import load_command_building


def build_initial_positions(num_drones: int, num_assets: int) -> tuple[np.ndarray, np.ndarray]:
    """VIPs and defenders on the **left** only (open space / building center-right)."""
    if num_drones <= num_assets:
        raise ValueError("num_drones must exceed num_assets (need at least one defender)")
    H = 0.12
    rows = []
    spacing = 0.14
    base_x = -0.38
    for a in range(num_assets):
        x = base_x + a * spacing
        rows.append([x, -0.32, H + 0.02 * a])
    n_def = num_drones - num_assets
    for k in range(n_def):
        rows.append([-0.44 + 0.12 * k, -0.1, H + 0.06 + 0.02 * k])
    xyz = np.array(rows, dtype=float)
    rpys = np.zeros((num_drones, 3), dtype=float)
    return xyz, rpys


def run(
    drone: DroneModel = DroneModel.CF2X,
    num_drones: int = 3,
    num_assets: int = 2,
    physics: Physics = Physics.PYB,
    gui: bool = True,
    record_video: bool = False,
    plot: bool = False,
    user_debug_gui: bool = False,
    obstacles: bool = False,
    simulation_freq_hz: int = 240,
    control_freq_hz: int = 48,
    duration_sec: int = 0,
    output_folder: str = "results",
    colab: bool = False,
    radar_hud: bool = False,
    verbose_render: bool = False,
    realtime_sync: bool = False,
    verbose_roles: bool = False,
    camera_orbit: bool = False,
    camera_orbit_speed: float = 14.0,
    camera_follow: bool = False,
    attack_ui: bool = True,
):
    if num_assets < 1:
        raise ValueError("num_assets must be >= 1")
    if num_drones <= num_assets:
        raise ValueError("Need num_drones > num_assets (at least one defender)")

    INIT_XYZS, INIT_RPYS = build_initial_positions(num_drones, num_assets)
    hold_xyz = INIT_XYZS[:num_assets].copy()
    vip_centroid0 = np.mean(hold_xyz, axis=0)

    env = CtrlAviary(
        drone_model=drone,
        num_drones=num_drones,
        initial_xyzs=INIT_XYZS,
        initial_rpys=INIT_RPYS,
        physics=physics,
        neighbourhood_radius=10,
        pyb_freq=simulation_freq_hz,
        ctrl_freq=control_freq_hz,
        gui=gui,
        record=record_video,
        obstacles=obstacles,
        user_debug_gui=user_debug_gui,
        radar_hud=radar_hud,
        verbose_render=verbose_render,
    )
    PYB_CLIENT = env.getPyBulletClient()

    building_id: int | None = None
    try:
        building_id = load_command_building(PYB_CLIENT, env.DRONE_IDS)
    except Exception as ex:
        print(f"[WARNING] Could not load central building URDF: {ex}")

    cam = None
    if gui:
        cam = GuiCameraController(
            PYB_CLIENT,
            orbit_enabled=camera_orbit,
            orbit_speed_deg_s=camera_orbit_speed,
            follow_drones=camera_follow,
        )

    attack_panel: AttackDebugUi | None = None
    if gui and attack_ui:
        attack_panel = AttackDebugUi(PYB_CLIENT)
        print(
            "[INFO] In the PyBullet **Params** panel: set **Red ATTACK type** (0=R,1=S,2=D), "
            "then drag **Red FIRE** to 1 and back to 0 to launch."
        )
    fleet = ThreatFleet(PYB_CLIENT, env.DRONE_IDS)
    if not gui or not attack_ui:
        fleet.spawn("rocket", vip_centroid0)

    logger = Logger(
        logging_freq_hz=control_freq_hz,
        num_drones=num_drones,
        output_folder=output_folder,
        colab=colab,
    )

    if drone not in [DroneModel.CF2X, DroneModel.CF2P]:
        raise ValueError("defender_pid demo expects CF2X or CF2P")
    ctrl = [DSLPIDControl(drone_model=drone) for _ in range(num_drones)]

    policy = DefenderPolicy(DefenderPolicyConfig(num_assets=num_assets))

    hud = getattr(env, "radar_hud", None)
    if duration_sec <= 0:
        max_steps = 10**9 if gui else int(12 * env.CTRL_FREQ)
    else:
        max_steps = int(duration_sec * env.CTRL_FREQ)

    if duration_sec <= 0 and gui:
        print(
            "[INFO] Unlimited defender run. Stop: Ctrl+C, close PyBullet, or radar Stop."
        )

    action = np.zeros((num_drones, 4))
    START = time.time()
    i = 0
    _radar_pause_last = 0.0
    sim_t = 0.0
    min_vip_clearance = float("inf")

    try:
        while i < max_steps:
            if gui and hasattr(p, "isConnected") and not p.isConnected(PYB_CLIENT):
                print("[INFO] PyBullet disconnected; exiting.")
                break

            if attack_panel is not None:
                try:
                    launch = attack_panel.poll_launch()
                except Exception:
                    launch = None
                if launch is not None:
                    try:
                        c = np.mean(env.pos[:num_assets], axis=0)
                        fleet.spawn(launch, c)
                        print(f"[INFO] Red team launched: {launch}")
                    except Exception as ex:
                        print(f"[WARNING] Red team spawn failed: {ex}")

            if hud is not None and hud.stop_requested:
                break
            while hud is not None and hud.paused and not hud.stop_requested:
                if attack_panel is not None:
                    try:
                        launch = attack_panel.poll_launch()
                    except Exception:
                        launch = None
                    if launch is not None:
                        try:
                            fleet.spawn(launch, np.mean(hold_xyz, axis=0))
                            print(f"[INFO] Red team launched (while paused): {launch}")
                        except Exception as ex:
                            print(f"[WARNING] Red team spawn failed: {ex}")
                now = time.monotonic()
                if now - _radar_pause_last >= (1.0 / 6.0):
                    hud.update(env.pos)
                    _radar_pause_last = now
                time.sleep(0.02)
            if hud is not None and hud.stop_requested:
                break

            obs, reward, terminated, truncated, info = env.step(action)
            if gui and hasattr(p, "isConnected") and not p.isConnected(PYB_CLIENT):
                print("[INFO] PyBullet disconnected; exiting.")
                break

            try:
                ipos, ivel = fleet.step(env.pos[:num_assets], env.CTRL_TIMESTEP)
            except Exception as ex:
                print(f"[WARNING] Threat step failed: {ex}")
                ipos, ivel = np.zeros(3), np.zeros(3)
            sim_t += env.CTRL_TIMESTEP
            threat_on = fleet.is_active()
            targets, roles = policy.compute_targets(
                env.pos,
                ipos,
                ivel,
                hold_xyz,
                sim_time=sim_t,
                threat_active=threat_on,
            )

            if threat_on:
                mc = fleet.min_clearance_vips(env.pos[:num_assets])
                min_vip_clearance = min(min_vip_clearance, mc)

            aim = fleet.closest_to(env.pos[0]) if threat_on else np.zeros(3)

            for j in range(num_drones):
                tp = targets[j]
                rpy = INIT_RPYS[j, :].copy()
                if j >= num_assets and threat_on:
                    dx = float(aim[0] - env.pos[j, 0])
                    dy = float(aim[1] - env.pos[j, 1])
                    rpy[2] = math.atan2(dy, dx)
                action[j, :], _, _ = ctrl[j].computeControlFromState(
                    control_timestep=env.CTRL_TIMESTEP,
                    state=obs[j],
                    target_pos=tp,
                    target_rpy=rpy,
                )

            for j in range(num_drones):
                rpy = INIT_RPYS[j, :].copy()
                if j >= num_assets and threat_on:
                    dx = float(aim[0] - env.pos[j, 0])
                    dy = float(aim[1] - env.pos[j, 1])
                    rpy[2] = math.atan2(dy, dx)
                ctrl_vec = np.hstack([targets[j], rpy, np.zeros(6)])
                logger.log(
                    drone=j,
                    timestamp=i / env.CTRL_FREQ,
                    state=obs[j],
                    control=ctrl_vec,
                )

            if verbose_roles or (i % max(1, int(2 * env.CTRL_FREQ)) == 0):
                print(f"[t={sim_t:5.2f}s] " + " | ".join(f"d{k}:{roles[k]}" for k in range(num_drones)))

            env.render()
            if gui and cam is not None:
                cen = None
                if camera_follow:
                    if threat_on:
                        cen = (np.sum(env.pos, axis=0) + ipos * len(fleet.agents)) / float(
                            num_drones + len(fleet.agents)
                        )
                    else:
                        cen = np.mean(env.pos, axis=0)
                cam.step(env.CTRL_TIMESTEP, drone_centroid_xyz=cen)
            if gui and realtime_sync:
                sync(i, START, env.CTRL_TIMESTEP)
            i += 1
    finally:
        try:
            client_ok = p.isConnected(PYB_CLIENT)
        except Exception:
            client_ok = False
        if client_ok:
            try:
                fleet.clear()
            except Exception:
                pass
            if building_id is not None:
                try:
                    p.removeBody(building_id, physicsClientId=PYB_CLIENT)
                except Exception:
                    pass
        try:
            env.close()
        except Exception:
            pass

    logger.save()
    logger.save_as_csv("defender_pid")
    if min_vip_clearance < float("inf"):
        print(f"[INFO] Closest red threat approach to any VIP (min 3D norm): {min_vip_clearance:.3f} m")
    if plot:
        logger.plot()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Defender demo + Red team ATTACK UI")
    parser.add_argument("--drone", type=DroneModel, default=DroneModel.CF2X, choices=DroneModel, metavar="")
    parser.add_argument("--num_drones", type=int, default=3, metavar="")
    parser.add_argument("--num_assets", type=int, default=2, metavar="")
    parser.add_argument("--physics", type=Physics, default=Physics.PYB, choices=Physics, metavar="")
    parser.add_argument("--gui", type=str2bool, default=True, metavar="")
    parser.add_argument("--record_video", type=str2bool, default=False, metavar="")
    parser.add_argument("--plot", type=str2bool, default=False, metavar="")
    parser.add_argument("--user_debug_gui", type=str2bool, default=False, metavar="")
    parser.add_argument("--obstacles", type=str2bool, default=False, metavar="")
    parser.add_argument("--simulation_freq_hz", type=int, default=240, metavar="")
    parser.add_argument("--control_freq_hz", type=int, default=48, metavar="")
    parser.add_argument("--duration_sec", type=int, default=0, metavar="")
    parser.add_argument("--output_folder", type=str, default="results", metavar="")
    parser.add_argument("--colab", type=bool, default=False, metavar="")
    parser.add_argument("--radar_hud", type=str2bool, default=False, metavar="")
    parser.add_argument("--verbose_render", type=str2bool, default=False, metavar="")
    parser.add_argument("--realtime_sync", type=str2bool, default=False, metavar="")
    parser.add_argument("--verbose_roles", type=str2bool, default=False, metavar="")
    parser.add_argument("--camera_orbit", type=str2bool, default=False, metavar="")
    parser.add_argument("--camera_orbit_speed", type=float, default=14.0, metavar="")
    parser.add_argument("--camera_follow", type=str2bool, default=False, metavar="")
    parser.add_argument(
        "--attack_ui",
        type=str2bool,
        default=True,
        metavar="",
        help="PyBullet Params sliders for red attack (default: True). False = auto rocket at start.",
    )
    ARGS = parser.parse_args()
    run(**vars(ARGS))

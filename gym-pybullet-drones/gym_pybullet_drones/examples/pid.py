"""Script demonstrating the joint use of simulation and control.

The simulation is run by a `CtrlAviary` environment.
The control is given by the PID implementation in `DSLPIDControl`.

Example
-------
In a terminal, run as:

    $ python pid.py

Notes
-----
The drones move, at different altitudes, along cicular trajectories 
in the X-Y plane, around point (0, -.3).

With ``--duration_sec 0`` (default): **GUI** runs until you close the PyBullet
window, press **Ctrl+C** in the terminal, or (if ``--radar_hud true``) click
**Stop** on the radar. **Headless** (``--gui false``) uses a 12s safety cap when
duration is 0 so automated tests finish. Use ``--duration_sec <seconds>`` for
a fixed-length run.

For smoother runs, ``--verbose_render`` stays off (no per-step console spam) and
``--realtime_sync`` is off by default (no extra sleeps); use ``--realtime_sync true``
if you want wall-clock pacing.

After the sim, ``logger.plot()`` can open a large Matplotlib **"Figure 1"** window;
``plt.show()`` blocks until you close it. That is disabled by default
(``--plot false``). Pass ``--plot true`` when you want those telemetry graphs.

**Camera (GUI):** mouse-drag still orbits the PyBullet view. Optional
``--camera_orbit true`` auto-rotates; ``--camera_follow true`` keeps the look-at
point on the drone swarm centroid. With the 3D view focused, **J/L** yaw,
**I/K** pitch, **U/O** zoom.

"""
import os
import time
import argparse
from datetime import datetime
import pdb
import math
import random
import numpy as np
import pybullet as p

from gym_pybullet_drones.utils.enums import DroneModel, Physics
from gym_pybullet_drones.envs.CtrlAviary import CtrlAviary
from gym_pybullet_drones.control.DSLPIDControl import DSLPIDControl
from gym_pybullet_drones.utils.Logger import Logger
from gym_pybullet_drones.utils.utils import sync, str2bool

DEFAULT_DRONES = DroneModel("cf2x")
DEFAULT_NUM_DRONES = 3
DEFAULT_PHYSICS = Physics("pyb")
DEFAULT_GUI = True
DEFAULT_RECORD_VISION = False
DEFAULT_PLOT = False
DEFAULT_USER_DEBUG_GUI = False
DEFAULT_OBSTACLES = True
DEFAULT_SIMULATION_FREQ_HZ = 240
DEFAULT_CONTROL_FREQ_HZ = 48
DEFAULT_DURATION_SEC = 0
DEFAULT_OUTPUT_FOLDER = 'results'
DEFAULT_COLAB = False
DEFAULT_RADAR_HUD = True
DEFAULT_VERBOSE_RENDER = False
DEFAULT_REALTIME_SYNC = False
DEFAULT_CAMERA_ORBIT = False
DEFAULT_CAMERA_ORBIT_SPEED = 14.0
DEFAULT_CAMERA_FOLLOW = False

def run(
        drone=DEFAULT_DRONES,
        num_drones=DEFAULT_NUM_DRONES,
        physics=DEFAULT_PHYSICS,
        gui=DEFAULT_GUI,
        record_video=DEFAULT_RECORD_VISION,
        plot=DEFAULT_PLOT,
        user_debug_gui=DEFAULT_USER_DEBUG_GUI,
        obstacles=DEFAULT_OBSTACLES,
        simulation_freq_hz=DEFAULT_SIMULATION_FREQ_HZ,
        control_freq_hz=DEFAULT_CONTROL_FREQ_HZ,
        duration_sec=DEFAULT_DURATION_SEC,
        output_folder=DEFAULT_OUTPUT_FOLDER,
        colab=DEFAULT_COLAB,
        radar_hud=DEFAULT_RADAR_HUD,
        verbose_render=DEFAULT_VERBOSE_RENDER,
        realtime_sync=DEFAULT_REALTIME_SYNC,
        camera_orbit=DEFAULT_CAMERA_ORBIT,
        camera_orbit_speed=DEFAULT_CAMERA_ORBIT_SPEED,
        camera_follow=DEFAULT_CAMERA_FOLLOW,
        ):
    #### Initialize the simulation #############################
    H = .1
    H_STEP = .05
    R = .3
    INIT_XYZS = np.array([[R*np.cos((i/6)*2*np.pi+np.pi/2), R*np.sin((i/6)*2*np.pi+np.pi/2)-R, H+i*H_STEP] for i in range(num_drones)])
    INIT_RPYS = np.array([[0, 0,  i * (np.pi/2)/num_drones] for i in range(num_drones)])

    #### Initialize a circular trajectory ######################
    PERIOD = 10
    NUM_WP = control_freq_hz*PERIOD
    TARGET_POS = np.zeros((NUM_WP,3))
    for i in range(NUM_WP):
        TARGET_POS[i, :] = R*np.cos((i/NUM_WP)*(2*np.pi)+np.pi/2)+INIT_XYZS[0, 0], R*np.sin((i/NUM_WP)*(2*np.pi)+np.pi/2)-R+INIT_XYZS[0, 1], 0
    wp_counters = np.array([int((i*NUM_WP/6)%NUM_WP) for i in range(num_drones)])

    #### Debug trajectory ######################################
    #### Uncomment alt. target_pos in .computeControlFromState()
    # INIT_XYZS = np.array([[.3 * i, 0, .1] for i in range(num_drones)])
    # INIT_RPYS = np.array([[0, 0,  i * (np.pi/3)/num_drones] for i in range(num_drones)])
    # NUM_WP = control_freq_hz*15
    # TARGET_POS = np.zeros((NUM_WP,3))
    # for i in range(NUM_WP):
    #     if i < NUM_WP/6:
    #         TARGET_POS[i, :] = (i*6)/NUM_WP, 0, 0.5*(i*6)/NUM_WP
    #     elif i < 2 * NUM_WP/6:
    #         TARGET_POS[i, :] = 1 - ((i-NUM_WP/6)*6)/NUM_WP, 0, 0.5 - 0.5*((i-NUM_WP/6)*6)/NUM_WP
    #     elif i < 3 * NUM_WP/6:
    #         TARGET_POS[i, :] = 0, ((i-2*NUM_WP/6)*6)/NUM_WP, 0.5*((i-2*NUM_WP/6)*6)/NUM_WP
    #     elif i < 4 * NUM_WP/6:
    #         TARGET_POS[i, :] = 0, 1 - ((i-3*NUM_WP/6)*6)/NUM_WP, 0.5 - 0.5*((i-3*NUM_WP/6)*6)/NUM_WP
    #     elif i < 5 * NUM_WP/6:
    #         TARGET_POS[i, :] = ((i-4*NUM_WP/6)*6)/NUM_WP, ((i-4*NUM_WP/6)*6)/NUM_WP, 0.5*((i-4*NUM_WP/6)*6)/NUM_WP
    #     elif i < 6 * NUM_WP/6:
    #         TARGET_POS[i, :] = 1 - ((i-5*NUM_WP/6)*6)/NUM_WP, 1 - ((i-5*NUM_WP/6)*6)/NUM_WP, 0.5 - 0.5*((i-5*NUM_WP/6)*6)/NUM_WP
    # wp_counters = np.array([0 for i in range(num_drones)])

    #### Create the environment ################################
    env = CtrlAviary(drone_model=drone,
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

    #### Obtain the PyBullet Client ID from the environment ####
    PYB_CLIENT = env.getPyBulletClient()

    from gym_pybullet_drones.utils.gui_camera import GuiCameraController
    cam = None
    if gui:
        cam = GuiCameraController(
            PYB_CLIENT,
            orbit_enabled=camera_orbit,
            orbit_speed_deg_s=camera_orbit_speed,
            follow_drones=camera_follow,
        )

    #### Initialize the logger #################################
    logger = Logger(logging_freq_hz=control_freq_hz,
                    num_drones=num_drones,
                    output_folder=output_folder,
                    colab=colab
                    )

    #### Initialize the controllers ############################
    if drone in [DroneModel.CF2X, DroneModel.CF2P]:
        ctrl = [DSLPIDControl(drone_model=drone) for i in range(num_drones)]

    #### Run length: duration_sec>0 = fixed; duration_sec<=0 = unbounded (GUI) or 12s cap (headless)
    hud = getattr(env, "radar_hud", None)
    if duration_sec <= 0:
        if gui:
            max_steps = 10**9
        else:
            max_steps = int(12 * env.CTRL_FREQ)
    else:
        max_steps = int(duration_sec * env.CTRL_FREQ)

    if duration_sec <= 0 and gui:
        print(
            "[INFO] Unlimited simulation (duration_sec=0, gui=True). "
            "Stop with: Ctrl+C in this terminal, close the PyBullet window, "
            "or run with --radar_hud true and click Stop on the radar."
        )

    #### Run the simulation ####################################
    action = np.zeros((num_drones,4))
    START = time.time()
    i = 0
    _radar_pause_last = 0.0
    while i < max_steps:

        if hud is not None and hud.stop_requested:
            break
        while hud is not None and hud.paused and not hud.stop_requested:
            now = time.monotonic()
            if now - _radar_pause_last >= (1.0 / 6.0):
                hud.update(env.pos)
                _radar_pause_last = now
            time.sleep(0.02)
        if hud is not None and hud.stop_requested:
            break

        #### Make it rain rubber ducks #############################
        # if i/env.SIM_FREQ>5 and i%10==0 and i/env.SIM_FREQ<10: p.loadURDF("duck_vhacd.urdf", [0+random.gauss(0, 0.3),-0.5+random.gauss(0, 0.3),3], p.getQuaternionFromEuler([random.randint(0,360),random.randint(0,360),random.randint(0,360)]), physicsClientId=PYB_CLIENT)

        #### Step the simulation ###################################
        obs, reward, terminated, truncated, info = env.step(action)
        if gui and hasattr(p, "isConnected") and not p.isConnected(PYB_CLIENT):
            print("[INFO] PyBullet GUI disconnected; exiting simulation loop.")
            break

        #### Compute control for the current way point #############
        for j in range(num_drones):
            action[j, :], _, _ = ctrl[j].computeControlFromState(control_timestep=env.CTRL_TIMESTEP,
                                                                    state=obs[j],
                                                                    target_pos=np.hstack([TARGET_POS[wp_counters[j], 0:2], INIT_XYZS[j, 2]]),
                                                                    # target_pos=INIT_XYZS[j, :] + TARGET_POS[wp_counters[j], :],
                                                                    target_rpy=INIT_RPYS[j, :]
                                                                    )

        #### Go to the next way point and loop #####################
        for j in range(num_drones):
            wp_counters[j] = wp_counters[j] + 1 if wp_counters[j] < (NUM_WP-1) else 0

        #### Log the simulation ####################################
        for j in range(num_drones):
            logger.log(drone=j,
                       timestamp=i/env.CTRL_FREQ,
                       state=obs[j],
                       control=np.hstack([TARGET_POS[wp_counters[j], 0:2], INIT_XYZS[j, 2], INIT_RPYS[j, :], np.zeros(6)])
                       # control=np.hstack([INIT_XYZS[j, :]+TARGET_POS[wp_counters[j], :], INIT_RPYS[j, :], np.zeros(6)])
                       )

        #### Printout ##############################################
        env.render()
        if gui and cam is not None:
            cen = np.mean(env.pos, axis=0) if camera_follow else None
            cam.step(env.CTRL_TIMESTEP, drone_centroid_xyz=cen)

        #### Sync the simulation ###################################
        if gui and realtime_sync:
            sync(i, START, env.CTRL_TIMESTEP)

        i += 1

    #### Close the environment #################################
    env.close()

    #### Save the simulation results ###########################
    logger.save()
    logger.save_as_csv("pid") # Optional CSV save

    #### Plot the simulation results ###########################
    if plot:
        logger.plot()

if __name__ == "__main__":
    #### Define and parse (optional) arguments for the script ##
    parser = argparse.ArgumentParser(description='Helix flight script using CtrlAviary and DSLPIDControl')
    parser.add_argument('--drone',              default=DEFAULT_DRONES,     type=DroneModel,    help='Drone model (default: CF2X)', metavar='', choices=DroneModel)
    parser.add_argument('--num_drones',         default=DEFAULT_NUM_DRONES,          type=int,           help='Number of drones (default: 3)', metavar='')
    parser.add_argument('--physics',            default=DEFAULT_PHYSICS,      type=Physics,       help='Physics updates (default: PYB)', metavar='', choices=Physics)
    parser.add_argument('--gui',                default=DEFAULT_GUI,       type=str2bool,      help='Whether to use PyBullet GUI (default: True)', metavar='')
    parser.add_argument('--record_video',       default=DEFAULT_RECORD_VISION,      type=str2bool,      help='Whether to record a video (default: False)', metavar='')
    parser.add_argument('--plot',               default=DEFAULT_PLOT,       type=str2bool,      help='Open Matplotlib telemetry plots after run (blocks until closed; default: False)', metavar='')
    parser.add_argument('--user_debug_gui',     default=DEFAULT_USER_DEBUG_GUI,      type=str2bool,      help='Whether to add debug lines and parameters to the GUI (default: False)', metavar='')
    parser.add_argument('--obstacles',          default=DEFAULT_OBSTACLES,       type=str2bool,      help='Whether to add obstacles to the environment (default: True)', metavar='')
    parser.add_argument('--simulation_freq_hz', default=DEFAULT_SIMULATION_FREQ_HZ,        type=int,           help='Simulation frequency in Hz (default: 240)', metavar='')
    parser.add_argument('--control_freq_hz',    default=DEFAULT_CONTROL_FREQ_HZ,         type=int,           help='Control frequency in Hz (default: 48)', metavar='')
    parser.add_argument('--duration_sec',       default=DEFAULT_DURATION_SEC,         type=int,           help='Seconds to run; 0 = unlimited in GUI (Ctrl+C / close window / radar Stop), 12s cap if headless (default: 0)', metavar='')
    parser.add_argument('--output_folder',     default=DEFAULT_OUTPUT_FOLDER, type=str,           help='Folder where to save logs (default: "results")', metavar='')
    parser.add_argument('--colab',              default=DEFAULT_COLAB, type=bool,           help='Whether example is being run by a notebook (default: "False")', metavar='')
    parser.add_argument('--radar_hud',        default=DEFAULT_RADAR_HUD, type=str2bool,   help='Matplotlib radar + XYZ when gui=True (default: True)', metavar='')
    parser.add_argument('--verbose_render',   default=DEFAULT_VERBOSE_RENDER, type=str2bool, help='Print full state every render() step (default: False)', metavar='')
    parser.add_argument('--realtime_sync',    default=DEFAULT_REALTIME_SYNC, type=str2bool, help='Wall-clock sync (sleep) to CTRL rate — adds lag (default: False)', metavar='')
    parser.add_argument('--camera_orbit',     default=DEFAULT_CAMERA_ORBIT, type=str2bool, help='Auto-rotate debug camera around scene (default: False)', metavar='')
    parser.add_argument('--camera_orbit_speed', default=DEFAULT_CAMERA_ORBIT_SPEED, type=float, help='Orbit rate in deg/s (default: 14)', metavar='')
    parser.add_argument('--camera_follow',    default=DEFAULT_CAMERA_FOLLOW, type=str2bool, help='Keep camera target on swarm centroid (default: False)', metavar='')
    ARGS = parser.parse_args()

    run(**vars(ARGS))

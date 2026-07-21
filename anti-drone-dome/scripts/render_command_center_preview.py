"""Render an offscreen command-center screenshot for visual regression review."""

import os
import sys

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pybullet
from pyqtgraph.Qt import QtWidgets

from scenarios import get_site_config
from sim.physics import PhysicsWorld
from viz.dashboard import Dashboard, SimControl


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dashboard = Dashboard(200.0, SimControl())
    dashboard.update({"type": "mission_start"})
    world = PhysicsWorld(gui=False, site_config=get_site_config())
    assets = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))
    pybullet.loadURDF(
        os.path.join(assets, "shahed136.urdf"),
        [320.0, 280.0, 135.0],
        physicsClientId=world.client,
    )
    pybullet.loadURDF(
        os.path.join(assets, "interceptor.urdf"),
        [80.0, -40.0, 65.0],
        globalScaling=1.8,
        physicsClientId=world.client,
    )
    base_state = {
        "dome_status": "TRACKING",
        "intruder_pos": (320.0, 280.0, 135.0),
        "interceptor_pos": (80.0, -40.0, 65.0),
        "radar_return": {
            "detected": True,
            "range": 441.0,
            "snr": 18.2,
        },
        "camera_return": {
            "detected": True,
            "source": "camera_segmentation",
        },
        "fused_track": {
            "detected": True,
            "source": "RADAR+EO",
            "confidence": 0.96,
        },
        "intruder_key": "shahed136",
        "pattern_key": "direct",
        "environment_name": "urban_haze",
        "visibility_m": 4500.0,
        "wind_mps": (4.0, 1.5, 0.0),
        "site_name": "Southern Ontario training site",
        "guidance_mode": "RESIDUAL AI + APN",
        "radar_station": (0.0, 0.0, 10.0),
        "predicted_intercept": (145.0, 90.0, 85.0),
        "intruder_speed": 51.0,
        "interceptor_speed": 62.0,
        "intruder_velocity": (-36.0, -34.0, -5.0),
        "interceptor_velocity": (43.0, 38.0, 24.0),
        "tti": 4.8,
        "track_confidence": 0.91,
        "events": ["Radar track confirmed", "EO correlation established"],
        "mission_time": 12.4,
        "sim_speed": 1.0,
        "real_time_factor": 0.14,
        "render_backend": world.render_backend + " + OSM",
    }
    for index, sim_time in enumerate(np.linspace(0.0, 12.0, 37)):
        fraction = sim_time / 12.0
        dashboard.update({
            **base_state,
            "intruder_pos": (
                720.0 - 400.0 * fraction,
                620.0 - 340.0 * fraction,
                215.0 - 80.0 * fraction,
            ),
            "interceptor_pos": (
                10.0 + 70.0 * fraction,
                -10.0 - 30.0 * fraction,
                5.0 + 60.0 * fraction,
            ) if sim_time >= 3.0 else None,
            "events": (
                ["Radar track acquired"] if index == 1
                else ["Interceptor engaged"] if abs(sim_time - 3.0) < 0.1
                else []
            ),
            "mission_time": float(sim_time),
        })
    reports = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "reports"))
    os.makedirs(reports, exist_ok=True)
    outputs = {
        "overview": "command_center_preview.png",
        "shahed": "tactical_shahed_view.png",
        "interceptor": "tactical_interceptor_view.png",
        "topdown": "tactical_topdown_view.png",
    }
    try:
        for mode, filename in outputs.items():
            dashboard._on_camera_view(mode)
            capture = world.capture_tactical_view(
                intruder_position=base_state["intruder_pos"],
                interceptor_position=base_state["interceptor_pos"],
                intruder_velocity=base_state["intruder_velocity"],
                interceptor_velocity=base_state["interceptor_velocity"],
                predicted_intercept=base_state["predicted_intercept"],
                view_mode=mode,
                include_metadata=True,
            )
            dashboard.update({
                **base_state,
                "events": [],
                "camera_frame": capture["frame"],
                "tactical_overlay": {
                    "view_mode": capture["view_mode"],
                    "screen_points": capture["screen_points"],
                },
            })
            app.processEvents()
            output = os.path.join(reports, filename)
            dashboard.grab().save(output)
            print(output)
    finally:
        dashboard.close()
        pybullet.disconnect(world.client)


if __name__ == "__main__":
    main()

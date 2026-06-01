"""Static scenario geometry for defender demos."""

from __future__ import annotations

import pkg_resources
import numpy as np
import pybullet as p


def _finesse_building_visuals(body_id: int, client: int) -> None:
    """Slightly richer shading where the PyBullet build supports it."""
    try:
        n = p.getNumJoints(int(body_id), physicsClientId=client)
    except Exception:
        n = 0
    for link in range(-1, max(0, n)):
        try:
            p.changeVisualShape(
                int(body_id),
                link,
                specularColor=[0.55, 0.55, 0.6],
                physicsClientId=client,
            )
        except Exception:
            pass


def load_command_building(physics_client_id: int, drone_ids=None) -> int:
    """Load a detailed **command building** (custom URDF) in the courtyard.

    Uses a multi-layer concrete + glass + roof asset for a much more realistic
    look than a plain cube. Collisions vs blue drones are **disabled** so flight
    near the façade stays stable.

    Returns the PyBullet body unique id (call ``p.removeBody`` on shutdown).
    """
    cid = int(physics_client_id)
    orn = p.getQuaternionFromEuler([0.0, 0.0, 0.0])
    #### Base on ground plane; footprint centered near scenario origin ##########
    pos = [0.0, -0.22, 0.0]
    urdf = pkg_resources.resource_filename(
        "gym_pybullet_drones", "assets/defender_command_building.urdf"
    )
    kwargs = dict(
        basePosition=pos,
        baseOrientation=orn,
        useFixedBase=True,
        flags=p.URDF_USE_MATERIAL_COLORS_FROM_MTL
        if hasattr(p, "URDF_USE_MATERIAL_COLORS_FROM_MTL")
        else 0,
        physicsClientId=cid,
    )
    try:
        bid = p.loadURDF(urdf, globalScaling=1.0, **kwargs)
    except TypeError:
        kwargs.pop("flags", None)
        try:
            bid = p.loadURDF(urdf, globalScaling=1.0, **kwargs)
        except TypeError:
            bid = p.loadURDF(urdf, **kwargs)
    p.resetBasePositionAndOrientation(int(bid), pos, orn, physicsClientId=cid)
    #### Freeze as scenery (no accidental tipping / drift) ######################
    try:
        p.changeDynamics(
            int(bid),
            -1,
            mass=0,
            linearDamping=1,
            angularDamping=1,
            physicsClientId=cid,
        )
    except Exception:
        pass
    _finesse_building_visuals(int(bid), cid)
    if drone_ids is not None:
        for did in np.atleast_1d(drone_ids).flatten():
            p.setCollisionFilterPair(
                int(bid), int(did), -1, -1, 0, physicsClientId=cid
            )
    return int(bid)

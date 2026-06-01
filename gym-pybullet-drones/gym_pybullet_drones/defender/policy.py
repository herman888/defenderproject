"""High-level geometry: who intercepts, who blocks on the LOS, who escorts in a ring."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class DefenderPolicyConfig:
    """Tuning for DefenderPolicy."""

    num_assets: int
    intercept_lead_sec: float = 0.55
    #### Intercept = blend(chord cut toward intruder, intruder + lead) ############
    intercept_chord_t: float = 0.58
    intercept_blend_intruder: float = 0.52
    #### Block = station along VIP→intruder at this fraction of chord length #####
    block_chord_t: float = 0.38
    escort_radius_m: float = 0.34
    escort_omega_rad_s: float = 1.0
    min_target_z: float = 0.1
    max_target_z: float = 0.55
    #### Match cruise altitude to VIPs (offset added in compute_targets) #########
    cruise_z_offset: float = 0.04


class DefenderPolicy:
    """Assigns world-frame position setpoints per drone index.

    Drones ``0 .. num_assets-1`` are **VIP / assets**: hold ``hold_xyz``.
    Drones ``num_assets .. N-1`` are **defenders**:

    - **Interceptor** — defender closest to a **cut point** on the segment
      ``VIP* → intruder`` (not simply closest to the intruder), so someone
      actually flies into the inbound corridor.
    - **Block** — second defender sits further out on the same chord
      (``block_chord_t``), between the VIP and the threat.
    - **Escort ring** — remaining defenders orbit the threatened VIP hold point.

    ``VIP*`` is the VIP whose **horizontal** separation to the intruder is
    smallest (altitude ignored so roll/pitch of the quad does not pick the wrong VIP).
    """

    def __init__(self, cfg: DefenderPolicyConfig):
        if cfg.num_assets < 1:
            raise ValueError("num_assets must be >= 1")
        self.cfg = cfg
        self._escort_phase = 0.0

    def compute_targets(
        self,
        positions: np.ndarray,
        intruder_pos: np.ndarray,
        intruder_vel: np.ndarray,
        hold_xyz: np.ndarray,
        sim_time: float,
    ) -> tuple[np.ndarray, list[str]]:
        """Return (N, 3) setpoints and a human-readable role per drone."""
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        n = positions.shape[0]
        A = self.cfg.num_assets
        if n < A + 1:
            raise ValueError("Need at least one defender (num_drones > num_assets)")
        hold_xyz = np.asarray(hold_xyz, dtype=float).reshape(A, 3)
        intruder_pos = np.asarray(intruder_pos, dtype=float).reshape(3)
        intruder_vel = np.asarray(intruder_vel, dtype=float).reshape(3)

        targets = np.zeros((n, 3), dtype=float)
        roles: list[str] = [""] * n

        for a in range(A):
            targets[a] = hold_xyz[a]
            roles[a] = "VIP (hold)"

        defenders = list(range(A, n))
        ip = intruder_pos.copy()
        iv = intruder_vel.copy()

        #### Primary VIP: closest in XY (ignore z) — stable threat pick ############
        ip_xy = ip.copy()
        ip_xy[2] = 0.0
        d2_xy = []
        for a in range(A):
            q = positions[a].copy()
            q[2] = 0.0
            d2_xy.append(float(np.linalg.norm(q - ip_xy)))
        primary = int(np.argmin(d2_xy))
        p_vip = positions[primary].copy()
        h_vip = hold_xyz[primary].copy()
        anchor_hold = h_vip.copy()

        chord = ip - p_vip
        chord_len = float(np.linalg.norm(chord))
        if chord_len < 1e-6:
            chord = np.array([1.0, 0.0, 0.0], dtype=float) * 0.01

        #### Cruise altitude band from VIP holds ##################################
        z_ref = float(np.median(hold_xyz[:, 2])) + self.cfg.cruise_z_offset

        #### Cut point on LOS (where we want the interceptor to go first) ########
        cut = p_vip + self.cfg.intercept_chord_t * chord
        lead = self.cfg.intercept_lead_sec * iv
        nose = ip + lead
        w = self.cfg.intercept_blend_intruder
        intercept_point = (1.0 - w) * cut + w * nose
        intercept_point[2] = float(np.clip(z_ref, self.cfg.min_target_z, self.cfg.max_target_z))

        #### Assign interceptor: closest defender to *cut* (corridor geometry) #####
        defenders_sorted = sorted(
            defenders,
            key=lambda d: float(np.linalg.norm(positions[d] - cut)),
        )
        d0 = defenders_sorted[0]
        targets[d0] = intercept_point
        roles[d0] = "defend (intercept)"

        remaining = [d for d in defenders if d != d0]

        if len(remaining) >= 1:
            #### Block: further along chord toward intruder #######################
            t_b = self.cfg.block_chord_t
            block_pt = p_vip + t_b * chord
            block_pt[2] = float(np.clip(z_ref, self.cfg.min_target_z, self.cfg.max_target_z))
            #### Second role: defender closest to block point (not intruder) #####
            d1 = min(remaining, key=lambda d: float(np.linalg.norm(positions[d] - block_pt)))
            targets[d1] = block_pt
            roles[d1] = "defend (block LOS)"
            remaining = [d for d in remaining if d != d1]

        if len(remaining) >= 1:
            self._escort_phase = self.cfg.escort_omega_rad_s * sim_time
            n_esc = len(remaining)
            for k, d in enumerate(remaining):
                ang = self._escort_phase + (2.0 * np.pi * k) / max(1, n_esc)
                off = self.cfg.escort_radius_m * np.array(
                    [np.cos(ang), np.sin(ang), 0.06], dtype=float
                )
                targets[d] = anchor_hold + off
                targets[d][2] = float(np.clip(z_ref, self.cfg.min_target_z, self.cfg.max_target_z))
                roles[d] = "defend (escort ring)"

        return targets, roles

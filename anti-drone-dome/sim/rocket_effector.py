"""
Micro-Rocket Effector Module for Project AEGIS / LARP.
Models high-speed boost-sustain kinetic micro-missiles (Mach 1.5 - 2.0)
for counter-swarm area thinning prior to terminal quadcopter intercept.
"""

import numpy as np

class MicroRocketEffector:
    """
    Simulates a high-acceleration solid-propellant micro-rocket interceptor.
    Flight phases:
    1. BOOST: High thrust (0 - 0.8s), accelerates to ~550 m/s (~Mach 1.6)
    2. SUSTAIN: Constant velocity cruise / coasting
    3. TERMINAL: Proportional Navigation (PN) guidance to collision point
    """

    def __init__(self, start_pos, target_pos, rocket_id=0):
        self.rocket_id = rocket_id
        self.pos = np.array(start_pos, dtype=float)
        self.vel = np.array([0.0, 0.0, 0.0], dtype=float)
        self.target_pos = np.array(target_pos, dtype=float)
        
        # Physical parameters
        self.mass = 2.2  # kg
        self.max_thrust = 1500.0  # N (Boost phase)
        self.burn_time = 0.8  # seconds
        self.drag_coeff = 0.25  # Aerodynamic drag coefficient
        self.cross_section = 0.005  # m^2 (80mm diameter rocket)
        self.air_density = 1.225  # kg/m^3
        
        # Guidance parameters
        self.nav_constant = 4.0  # Proportional navigation gain N
        self.time_elapsed = 0.0
        self.is_active = True
        self.intercepted = False
        self.detonation_radius = 4.0  # 4-meter lethal fragmentation sphere
        self.cost_dollars = 1800.0  # Unit cost in USD

        # Initial launch vector towards target
        direction = self.target_pos - self.pos
        norm = np.linalg.norm(direction)
        if norm > 0:
            self.unit_dir = direction / norm
        else:
            self.unit_dir = np.array([0.0, 0.0, 1.0])

    def step(self, dt, current_target_pos, target_vel=np.zeros(3)):
        """
        Advances physics and guidance by dt seconds.
        """
        if not self.is_active:
            return self.pos, self.intercepted

        self.time_elapsed += dt
        self.target_pos = np.array(current_target_pos, dtype=float)
        
        # 1. Thrust Calculation (Boost vs Coast)
        if self.time_elapsed <= self.burn_time:
            thrust_force = self.unit_dir * self.max_thrust
        else:
            thrust_force = np.zeros(3)

        # 2. Aerodynamic Drag Calculation
        speed = np.linalg.norm(self.vel)
        if speed > 0:
            drag_force = -0.5 * self.air_density * (speed ** 2) * self.drag_coeff * self.cross_section * (self.vel / speed)
        else:
            drag_force = np.zeros(3)

        # 3. Proportional Navigation Guidance Acceleration Command
        r_vec = self.target_pos - self.pos
        distance = np.linalg.norm(r_vec)

        if distance < self.detonation_radius:
            self.intercepted = True
            self.is_active = False
            return self.pos, self.intercepted

        if distance > 0 and speed > 10.0:
            v_rel = np.array(target_vel) - self.vel
            los_rate = np.cross(r_vec, v_rel) / (distance ** 2)
            accel_pn = self.nav_constant * speed * np.cross(los_rate, r_vec / distance)
        else:
            accel_pn = np.zeros(3)

        # 4. Total Acceleration and Kinematic Update
        gravity = np.array([0.0, 0.0, -9.81])
        total_accel = (thrust_force + drag_force) / self.mass + gravity + accel_pn
        
        self.vel += total_accel * dt
        self.pos += self.vel * dt
        
        if speed > 1.0:
            self.unit_dir = self.vel / speed

        return self.pos, self.intercepted

    def get_state(self):
        """Returns rocket state telemetry dictionary."""
        return {
            "id": self.rocket_id,
            "pos": self.pos.tolist(),
            "vel": self.vel.tolist(),
            "speed": float(np.linalg.norm(self.vel)),
            "active": self.is_active,
            "intercepted": self.intercepted,
            "cost_usd": self.cost_dollars
        }

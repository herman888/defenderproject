"""
Passive Monocular Optical Tracking Module for AEGIS / LARP.
Enables radar-free, stealth tracking using camera bounding box geometry
and monocular depth estimation for EW-jammed environments.
"""

import numpy as np

class PassiveOpticalTracker:
    """
    Tracks target 3D kinematics from 2D monocular camera bounding boxes.
    Uses target bounding area (pixels) to estimate range via inverse square law.
    """

    def __init__(self, focal_length_px=800.0, reference_wingspan_m=0.8):
        self.focal_length = focal_length_px
        self.reference_wingspan = reference_wingspan_m  # Assumed nominal target width in meters
        
        # State vector: [x, y, z, vx, vy, vz]
        self.state = np.zeros(6)
        self.initialized = False
        self.last_timestamp = 0.0

    def update_from_bbox(self, bbox, timestamp, camera_pos, camera_ori_matrix):
        """
        Updates tracking state from a 2D bounding box detection:
        bbox: [x_center_px, y_center_px, width_px, height_px]
        camera_pos: [x, y, z] position of interceptor camera in ENU world frame
        camera_ori_matrix: 3x3 rotation matrix from camera frame to world frame
        """
        u, v, w, h = bbox
        
        # 1. Estimate Range using inverse pinhole projection
        if w > 0:
            estimated_range = (self.reference_wingspan * self.focal_length) / w
        else:
            estimated_range = 100.0

        # 2. Compute unit ray vector in camera frame (Z-forward, X-right, Y-down)
        ray_cam = np.array([
            (u - 640.0) / self.focal_length,
            (v - 360.0) / self.focal_length,
            1.0
        ])
        ray_cam /= np.linalg.norm(ray_cam)

        # 3. Transform ray to World Frame (ENU)
        ray_world = camera_ori_matrix @ ray_cam

        # 4. Compute 3D target position estimate
        target_pos_est = np.array(camera_pos) + ray_world * estimated_range

        # 5. Velocity estimation via finite differences
        if not self.initialized:
            self.state[:3] = target_pos_est
            self.state[3:] = np.zeros(3)
            self.initialized = True
        else:
            dt = max(timestamp - self.last_timestamp, 0.001)
            meas_vel = (target_pos_est - self.state[:3]) / dt
            
            # Alpha-Beta filter smoothing
            alpha = 0.4
            beta = 0.2
            
            residual = target_pos_est - self.state[:3]
            self.state[:3] += alpha * residual
            self.state[3:] += (beta / dt) * residual

        self.last_timestamp = timestamp
        return self.state[:3].copy(), self.state[3:].copy()

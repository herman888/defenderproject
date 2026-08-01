"""Multi-effector UDP telemetry extension for tactical stream."""

import json
from typing import List, Dict, Any
from integration.tactical_stream import TacticalUdpPublisher

class MultiEffectorTelemetryPublisher:
    """
    Wraps the existing TacticalUdpPublisher to include micro-rocket track data 
    alongside the existing interceptor/intruder tracks.
    """
    
    def __init__(self, publisher: TacticalUdpPublisher):
        """
        Initialize with an existing TacticalUdpPublisher.
        
        Args:
            publisher (TacticalUdpPublisher): The underlying publisher to use.
        """
        self.publisher = publisher
        
    def broadcast_rocket_effector_state(self, base_state: dict, rockets: List[Dict[str, Any]]) -> dict:
        """
        Broadcasts rocket effector state (position, velocity, active status, cost) 
        as additional track entries alongside standard tactical telemetry.
        
        Args:
            base_state (dict): The standard tactical state to broadcast.
            rockets (list): A list of rocket state dictionaries.
            
        Returns:
            dict: The published packet.
        """
        state = dict(base_state)
        tracks = dict(state.get("tracks", {}))
        
        for i, rocket in enumerate(rockets):
            rocket_id = rocket.get("id", f"rocket_{i}")
            tracks[rocket_id] = {
                "id": rocket_id,
                "role": "effector",
                "asset_id": "micro_rocket",
                "type": "rocket",
                "position_enu_m": rocket.get("position_enu_m", [0.0, 0.0, 0.0]),
                "velocity_enu_mps": rocket.get("velocity_enu_mps", [0.0, 0.0, 0.0]),
                "orientation_xyzw": rocket.get("orientation_xyzw", [0.0, 0.0, 0.0, 1.0]),
                "active": rocket.get("active", True),
                "cost": rocket.get("cost", 500.0)
            }
            
        state["tracks"] = tracks
        return self.publisher.publish(state)
        
    def broadcast_cpk_summary(self, effectors_used: int, threats_destroyed: int, total_cost: float, total_value_destroyed: float) -> dict:
        """
        Sends a JSON summary packet with cost-per-kill metrics.
        
        Args:
            effectors_used (int): Total number of effectors used.
            threats_destroyed (int): Total number of threats destroyed.
            total_cost (float): Total cost of effectors used.
            total_value_destroyed (float): Total value of threats destroyed.
            
        Returns:
            dict: The summary data sent.
        """
        summary = {
            "type": "cpk_summary",
            "effectors_used": effectors_used,
            "threats_destroyed": threats_destroyed,
            "total_cost": total_cost,
            "total_value_destroyed": total_value_destroyed,
        }
        
        payload = json.dumps(summary).encode('utf-8')
        
        # Send raw JSON over the UDP socket bypassing the tactical schema validation
        self.publisher._socket.sendto(payload, (self.publisher.endpoint.host, self.publisher.endpoint.port))
        
        if self.publisher._recording is not None:
            self.publisher._recording.write(payload + b"\n")
            self.publisher._recording.flush()
            
        return summary

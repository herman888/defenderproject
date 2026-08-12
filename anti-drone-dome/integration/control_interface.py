"""Non-transmitting control-interface boundary for bench traceability only.

No implementation in this module opens a serial port, socket, or radio link.
Hardware control remains deliberately unavailable pending separately documented
failsafe qualification and explicit approval.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ControlIntent:
    timestamp_ns: int
    source_track_id: str
    mode: str
    rationale: str


class ControlInterface:
    transport = "abstract"
    def record_intent(self, intent: ControlIntent) -> dict: raise NotImplementedError


class MspBenchLog(ControlInterface):
    """Bench-only implementation: reports the intended action and never transmits."""
    transport = "msp-bench-log"
    def record_intent(self, intent: ControlIntent) -> dict:
        return {"schema": "larp.control-intent.v1", "transport": self.transport,
                "transmitted": False, "intent": asdict(intent)}


class MavlinkBenchLog(MspBenchLog):
    transport = "mavlink-bench-log"

"""Visualization package.

Keep the package import lightweight so headless CI can load ACMI / non-UI
helpers without requiring PyQt6. Import Dashboard from viz.dashboard directly
when you need the UI.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ACMIWriter", "Dashboard", "SimControl", "altitude_time_window"]


def __getattr__(name: str) -> Any:
    if name == "ACMIWriter":
        from .acmi_writer import ACMIWriter

        return ACMIWriter
    if name in {"SimControl", "altitude_time_window", "_altitude_time_window"}:
        from . import sim_control as _sim_control

        return getattr(_sim_control, name)
    if name == "Dashboard":
        from .dashboard import Dashboard

        return Dashboard
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

#!/usr/bin/env python3
"""IDE-friendly entry point (some run configs are named ``run_sim``).

Same program as ``main.py``: PyBullet GUI + matplotlib dashboard + terminal menus.

**Requires PyBullet in your active Python** — activate a venv first, e.g.::

    source ../gym-pybullet-drones/.venv/bin/activate
    python3 run_sim.py

Or on macOS: ``bash run_mac.sh`` (auto-picks a venv). See README.md.
"""

from main import main

if __name__ == "__main__":
    main()

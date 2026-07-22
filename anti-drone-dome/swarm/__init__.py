"""Autonomous swarm coordination: airborne coordinator directing an interceptor swarm.

This package adds a swarm layer on top of the single-target interception core. A
physical airborne *coordinator* node assigns a swarm of interceptors to a saturation
attack of many threats, over a range-dependent RF link, with autonomous re-tasking
when threats are neutralised, new threats appear, or interceptors lose link.

The coordination brain (`rf_link`, `assignment`, `coordinator`) is substrate
independent: it operates only on plain ENU state dicts and never imports PyBullet, so
it is reused unchanged by the headless point-mass runner (`runner`) and the optional
PyBullet path in `main.py`.
"""

from __future__ import annotations

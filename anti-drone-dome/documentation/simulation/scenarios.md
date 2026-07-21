# Scenarios, environments, and maps

## Interactive mission space

The command center exposes three intruder classes, six route profiles, and six
weather/EW environments. Procedural training samples continuously within and
between those named regimes rather than memorizing a fixed menu.

Route profiles:

- direct
- nap-of-earth
- spiral
- crossing
- pop-up
- offset

The environment randomizes launch bearing and range, interceptor position,
wind, mass, actuator response, battery thrust, radar noise, sensor dropout,
latency, and target evasion.

## Operational stress catalog

The versioned `scenario_data/regression_campaign_v1.json` catalog contains:

| ID | Primary stress |
|---|---|
| `baseline-direct` | Clear direct reference |
| `terrain-mask-low` | Low altitude, dropout, and terrain mask |
| `crosswind-crossing` | Crossing geometry and high wind |
| `degraded-track` | Latency, noise, and intermittent track |
| `agile-pop-up` | Evasive pop-up target |
| `remote-launch` | Displaced interceptor geometry |
| `spiral-noisy` | Spiral route and degraded sensing |
| `compound-edge` | Combined maximum-stress edge case |

Each episode records its scenario ID and deterministic seed.

## Real map cache

`scripts/download_osm_map.py` downloads roads and buildings around the approved
site in `scenario_data/southern_ontario.json`. The cache allows later offline
simulation. OSM data remains subject to OpenStreetMap attribution and the Open
Database License.

!!! warning
    Public map geometry improves context; it does not establish surveyed
    obstacle accuracy or flight authorization.


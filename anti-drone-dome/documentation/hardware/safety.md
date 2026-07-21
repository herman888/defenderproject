# Hardware safety and integration policy

## Default posture

- Physical actuation is disabled.
- Betaflight/MSP profiles are read-only.
- SITL arming requires explicit acknowledgement.
- Props remain removed for firmware, USB, receiver, and motor-direction work.
- A passing synthetic campaign does not authorize flight.

## Required path to controlled hardware testing

1. Select and validate the command protocol.
2. Characterize vehicle mass, acceleration, speed, battery, and actuator lag.
3. Calibrate radar/EO timing and coordinate transforms.
4. Align approved flight logs against simulation.
5. Pass repeatable SIL and HIL gates.
6. Implement independent geofence, abort, and loss-of-link behavior.
7. Complete independent safety, legal, and range approval.

## Protocol decision

The current command path is MAVLink/ArduPilot oriented. The lab boards run
Betaflight/MSP. Choose one of these before command integration:

- migrate a suitable controller to ArduPilot and retain MAVLink;
- implement and independently validate a constrained MSP bridge;
- use a companion computer with an approved autopilot interface.

Telemetry-only MSP inspection can proceed without making that actuation choice.


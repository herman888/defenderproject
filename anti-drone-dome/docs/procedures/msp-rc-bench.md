# MSP RC bench research boundary

The installed firmware version is **NOT VERIFIED** on the attached controller.
Betaflight's published MSP reference identifies `MSP_SET_RAW_RC` (ID 200) as an
FC-bound message with eight RC channels; this identifies a candidate message but
does not qualify its behaviour on this board or release. See the [MSP protocol
reference](https://betaflight.com/docs/development/MSP-Protocol-Reference-Dev) and
the [source constant](https://github.com/betaflight/betaflight/blob/master/src/main/msp/msp_protocol.h).

No MSP transmission is implemented. `integration/control_interface.py` supports
only a bench log that records `transmitted: false`; MSP and MAVLink implementations
share that non-transmitting interface. A flight-capable transport is explicitly out
of scope until a separate approval and qualification change.

Before any future transmission test: remove props, disconnect the flight battery,
and document the controller version, receiver configuration, actual failsafe values,
and observed RX-loss behaviour. Betaflight says FC failsafe monitors absent/bad RX
data and its configured stages; valid input during Stage 1 can stop that process.
Therefore interaction between MSP-fed values, a receiver-loss condition, and the
configured failsafe is **NOT VERIFIED** here and must not be assumed. Use the
official [failsafe guide](https://betaflight.com/docs/wiki/guides/current/Failsafe)
to define the bench procedure before enabling any transport.

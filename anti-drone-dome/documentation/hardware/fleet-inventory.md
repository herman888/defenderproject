# Flight-controller and receiver fleet inventory

This inventory is keyed by **MCU unique ID**, not transient Windows COM port.
No row is promoted from a photograph or a board-family label.

| MCU unique ID / key | Airframe | Firmware / board | MCU | Internal flash | External dataflash | UARTs | Receiver | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mcu-uid-NOT-MEASURED` | `NOT MEASURED` | Betaflight 2025.12.5 / `FURYF4OSD` | STM32F40X | `NOT MEASURED` | 16 Mbit JEDEC `0x00ef4018` | VCP, UART1, UART3, UART6: no assigned serial functions | Configured `SPEK2048`; physical RX `NOT MEASURED`; no live signal (`RXLOSS`, RX rate 0) | Measured read-only dump |
| `NOT MEASURED` | `NOT MEASURED` | `NOT MEASURED` | `NOT MEASURED` | `NOT MEASURED` | `NOT MEASURED` | `NOT MEASURED` | `NOT MEASURED` | Awaiting fleet interrogation |

`SPEK2048` is evidence of a real fleet-level Spektrum RC ecosystem, not a stale
configuration claim. It does **not** establish that this FURYF4OSD presently has
a physically mounted, bound receiver: its receiver signal is absent. Inventory
the Spektrum transmitter and every loose/mounted satellite or receiver to find a
bound pairing before buying a RadioMaster Pocket.

## ArduPilot decision rule

The companion-guidance path requires GUIDED mode. ArduPilot documents reduced
firmware for boards with 1 MB flash, and says its BETAFPV F405 family should use
only ACRO, STABILIZE, and ALTHOLD for safest operation; that board therefore does
not meet this project's GUIDED requirement. [Firmware limitations](https://ardupilot.org/copter/docs/common-limited-firmware.html)
and the [BETAFPV F405 documentation](https://en.ardupilot.org/copter/docs/common-betafpvf405.html)
are the governing sources.

An `F7` label is insufficient: STM32F722 has 512 KB, F745 is commonly 1 MB, and
F765 is 2 MB. The exact MCU marking, internal flash measurement, supported
ArduPilot target, current firmware size, and margin must be recorded for each
board. No flashing is authorized by this inventory pass. The current FURYF4OSD
has no identified official ArduPilot target; its target and margin remain **NOT
MEASURED**.

## Collection instructions

Bring every FC, the Spektrum transmitter, and all loose or mounted receivers/
satellites. Run `bench_fc_readonly.py --port COMx --airframe-id <id>
--confirm-props-removed-no-battery` once per board. The script uses only its
hard-whitelisted read commands and writes an MCU-UID-keyed artifact; if firmware
does not expose a UID, it explicitly records `mcu-uid-NOT-MEASURED` rather than
falling back to a COM number.

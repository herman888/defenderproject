# Spektrum radio

Both lab quads use a **Spektrum DX4e** (Mode 2) with a **satellite receiver**.

---

## Wiring (Omnibus SBUS pad)

| Sat wire | FC pad |
|----------|--------|
| Signal (white/yellow) | **SBUS** |
| + | **3.3V** (not 5V) |
| − | **GND** |

!!! warning
    The Omnibus **SBUS** pad has a hardware inverter for SBUS. Spektrum serial is non-inverted — you may need `set serialrx_inverted = ON` in CLI (try OFF if channels look wrong).

---

## Betaflight Ports

| Port | MSP | Serial Rx |
|------|-----|-----------|
| USB VCP | ON | **OFF** |
| UART1 | OFF | **ON** |
| UART3 / UART6 | OFF | OFF |

Save and Reboot after changes.

---

## Receiver settings

**CLI** (copy exactly):

```
set serialrx_provider = SPEK2048OR2048
set serialrx_inverted = ON
save
```

Or in the UI: Serial Receiver Provider → **SPEKTRUM1024** / **2048**.

**Channel map:** `AETR1234` (Mode 2: right stick = roll/pitch, left = throttle/yaw).

---

## Stick test (Receiver tab)

| You move | Bars that should change |
|----------|-------------------------|
| Right stick left/right | Roll only |
| Right stick up/down | Pitch only |
| Left stick up/down | Throttle |
| Left stick left/right | Yaw |
| Switches | AUX only |

Throttle at rest should sit near **1000–1100**, not everything pegged at **1915**.

If **one stick moves every bar**, polarity / decode is wrong — flip `serialrx_inverted`, re-bind, or reflash with **Spektrum** (not Core Only / CRSF).

---

## Bind

1. Bind plug in satellite  
2. Battery on → wait for **solid** LED  
3. Remove bind plug → power cycle  

Flashing LED = not bound.

---

## Arming (props off)

1. Disconnect Configurator (USB unplugged)  
2. Battery on  
3. Throttle down + yaw right ~2 seconds  
   (or arm AUX switch if set in Modes)

---

## Fury notes

After Spektrum flash: **Receiver → SPEKTRUM2048** and enable Serial Rx on the UART wired to the sat. Use `setup_fury_radio.sh` for step-by-step.

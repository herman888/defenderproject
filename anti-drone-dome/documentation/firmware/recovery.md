# Flight-controller recovery

When the FC will not connect normally (no blink LED, empty port dropdown, or stuck in DFU).

---

## Stuck in DFU / no normal USB

1. Unplug USB, wait 10 s  
2. Plug **without** holding BOOT (battery on)  
3. Port should be **OMNIBUSF4SD** / **usbmodem**, not BOOTLOADER  

If still BOOTLOADER: click **Exit DFU Mode** in Firmware Flasher, or power-cycle battery while USB stays in the Mac.

---

## Mass-erase DFU flash

Clears corrupt firmware and rewrites Spektrum build:

```bash
# Omnibus
cd anti-drone-dome/scripts
bash fix_omnibus_dfu_flash.sh

# Fury
bash fix_fury_dfu_flash.sh
```

Enter DFU first (BOOT + USB). `dfuERROR / corrupt` before erase is common — scripts clear status and continue.

---

## Omnibus USB dead (no serial, no DFU)

Try in order:

1. Data USB cable (not charge-only), direct Mac port, battery + USB  
2. Wiggle micro-USB at the FC  
3. BOOT + USB again  

If Mac never sees DFU:

### ST-Link recovery

```bash
brew install stlink
bash anti-drone-dome/scripts/stlink_recover_fc.sh
```

Wire **GND, SWDIO, SWCLK** to FC pads (bottom / SWD — not SBUS edge pads). Power with battery. Uses `st-flash` to write the cloud hex.

---

## Mac prerequisites

```bash
brew install dfu-util
brew install stlink   # Omnibus fallback only
```

---

## Checklist after recovery

| Check | Expected |
|-------|----------|
| LED after normal plug | Blinking |
| Port dropdown | Board name / usbmodem |
| `dfu-util -l` after normal plug | No DFU device |
| Receiver sticks | Independent channels |

Then: [Flashing](flashing.md) post-flash radio steps · [Radio](../hardware/radio.md)

# Flashing

Flash Betaflight via **DFU** (`dfu-util`) or [app.betaflight.com](https://app.betaflight.com). Prefer a **Spektrum** cloud build for DX4e (not Core Only / CRSF-only).

---

## Safety

1. **Props off**
2. Quit Chrome / Configurator if the serial port is busy (`Cmd+Q` on Mac)
3. Battery optional for flash; recommended for motor tests

---

## Enter DFU

1. Unplug USB  
2. Hold **BOOT** on the FC  
3. Plug USB while holding BOOT  
4. Release after ~3 seconds  

Confirm:

```bash
dfu-util -l
# expect Found DFU: [0483:df11] ...
```

In Configurator the port should show **STM32 BOOTLOADER**. No blinking status LED in DFU is normal.

---

## Script flash (recommended on Mac)

### Omnibus Spektrum recovery

```bash
cd anti-drone-dome/scripts
# Cmd+Q Chrome first
bash fix_omnibus_dfu_flash.sh
# or
bash setup_omnibus_f4.sh --spektrum
```

### Fury Spektrum

```bash
bash fix_fury_dfu_flash.sh
# or
bash setup_fury_f4.sh --flash
```

Scripts download a cloud hex to `/tmp/bf_<TARGET>_<RELEASE>*.hex` and run `dfu-util`.

---

## DFU flow (both boards)

1. Props off; quit Configurator  
2. Enter DFU (`bl` in CLI, or BOOT + USB)  
3. Flash with script or Configurator  
4. Unplug USB, wait **5–10 s**, replug **without** BOOT  
5. Status LED should **blink**; port becomes `/dev/cu.usbmodem*`  
6. Connect in Configurator → set Ports / Receiver  

**Motor test (USB working):**

```bash
python3 anti-drone-dome/scripts/betaflight_motor_test.py
```

---

## Browser Configurator notes

Web Configurator often shows `firmwareFlasherNoPortSelected` on Mac even when DFU is visible. Fixes to try:

- **No reboot sequence ON** when already in DFU  
- Connect green button before Flash  
- Allow Chrome USB permission for STM32 BOOTLOADER  
- Or flash with `dfu-util` / project scripts (most reliable)

Build options when using the UI:

| Setting | Value |
|---------|--------|
| Target | `OMNIBUSF4SD` or `FURYF4OSD` |
| Full chip erase | ON |
| Core Only | **OFF** |
| Radio | **SPEKTRUM** |
| Motor | DSHOT |

---

## After flash — radio checklist

1. Ports: UART1 Serial Rx **ON**, USB VCP Serial Rx **OFF**  
2. CLI: `set serialrx_provider = SPEK2048OR2048` + `serialrx_inverted` ON/OFF as needed  
3. Receiver tab stick test  

See [Radio](../hardware/radio.md).

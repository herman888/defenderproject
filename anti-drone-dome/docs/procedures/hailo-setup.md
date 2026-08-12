# Hailo AI HAT+ setup and bring-up

This procedure is for the person physically holding the Raspberry Pi 5 and Hailo
AI HAT+. It creates an evidence record whether the device works or fails.

## Before installing

Use current Raspberry Pi OS (64-bit) and the Hailo packages supplied for that OS.
The Pi 5 needs PCIe enabled. In `/boot/firmware/config.txt`, record the values
actually used on the day; do not copy a claimed result into this table.

| Item | Day-of-run value |
| --- | --- |
| Raspberry Pi OS version | TO BE MEASURED |
| `dtparam=pciex1` value | TO BE MEASURED |
| HailoRT version | TO BE MEASURED |
| PCIe driver version | TO BE MEASURED |
| Hailo firmware version | TO BE MEASURED |
| Dataflow Compiler version | TO BE MEASURED |
| `hailortcli fw-control identify` result | TO BE MEASURED |
| Idle temperature | TO BE MEASURED |
| Idle power (external inline meter) | TO BE MEASURED |

Install the OS-matched runtime bundle from Hailo's Developer Zone or the Raspberry
Pi AI software guide. Do not mix versions: record HailoRT, the PCIe driver, device
firmware, and Dataflow Compiler together. A mismatch between these is a common
bring-up failure. Reboot after installing a kernel driver, then confirm that
`hailortcli fw-control identify` and `hailortcli scan` run.

## Running this and sending the results back.

Copy and run these commands exactly, replacing only the placeholders in angle
brackets. They work whether this is a success or a failure run.

```bash
git clone <repository-url> anti-drone-dome
cd anti-drone-dome
git checkout feat/pre-camera-sprint
git pull --ff-only origin feat/pre-camera-sprint
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install psutil
python scripts/hailo_bringup.py --operator <yourname> --idle-power-w <reading-from-inline-meter>
ls -lt artifacts/hailo/
```

The final command confirms the newly written artifact in `artifacts/hailo/`. If no
power meter is available, omit `--idle-power-w`; the artifact will correctly say
`NOT MEASURED`. If the first run fails and you fix something, rerun with
`--resolution-note "<what changed>"` so both failure and resolution are retained.

Artifact commits use `<subsystem>: <what was run> on <host>, <result>`. Commit
artifacts only—no code changes in an artifact commit. Commit a failure with `fail`;
it is data. Do not amend, rebase, or squash artifact commits: the artifact records
the producing commit hash and rewriting history breaks that link.

```bash
git checkout -b hailo/bringup-<yourname>
git add artifacts/hailo/
git commit -m "hailo: bring-up run on <host>, <pass|fail|partial>"
git push -u origin hailo/bringup-<yourname>
```

Reply with only the result (`pass`, `fail`, or `partial`) and the branch name.

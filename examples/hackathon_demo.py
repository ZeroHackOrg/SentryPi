#!/usr/bin/env python3
"""SentryPi hackathon table demo — two realistic traces on the REAL pipeline.

  Trace 1  examples/living_room.pi   compiles clean, emits artifacts, drives
                                    the appliance (green LED)
  Trace 2  examples/device_fault.pi  Safe-Fail firewall blocks the corrupted
                                    stream (exit code 2), nothing is emitted
                                    and the hardware stays disengaged (red LED)

Optional hardware (Raspberry Pi only): run with sudo. When /sys/class/gpio is
unavailable the demo runs as a pure software narration.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sentrypi import compiler

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"

GREEN_BCM = 18  # appliance ON indicator
RED_BCM = 23    # Safe-Fail lockdown indicator


def _sysfs_set(pin, value):
    base = f"/sys/class/gpio/gpio{pin}"
    try:
        if not os.path.exists(base):
            with open("/sys/class/gpio/export", "w", encoding="utf-8") as handle:
                handle.write(str(pin))
        with open(f"{base}/direction", "w", encoding="utf-8") as handle:
            handle.write("out")
        with open(f"{base}/value", "w", encoding="utf-8") as handle:
            handle.write(str(value))
        return True
    except OSError:
        return False


def led(green, red):
    _sysfs_set(GREEN_BCM, 1 if green else 0)
    _sysfs_set(RED_BCM, 1 if red else 0)


def artifacts(result):
    return [p for p in (result.bin_path, result.map_path, result.sh_path, result.driver_path) if p]


def main():
    print("=" * 72)
    print("SENTRYPI (.pi) — HUMAN-CENTRIC COMPILER FOR SAFE EDGE AUTOMATION")
    print("=" * 72)

    work = Path(tempfile.mkdtemp(prefix="sentrypi-demo-"))

    print("\n----- TRACE 1 : healthy smart-home script (living_room.pi) -----\n")
    first = compiler.compile_file(
        str(EXAMPLES / "living_room.pi"), output_dir=str(work), report=print
    )
    print(f"[compiler] ok={first.ok}  warnings={len(first.warnings)}")
    print(f"[compiler] artifacts emitted: {artifacts(first) or 'NONE'}")
    if first.ok and first.sh_path:
        print("[compiler] executing the safe sysfs mapping...")
        subprocess.run(["bash", first.sh_path], check=False)
        led(green=True, red=False)
        print("\n[compiler] GREEN appliance line ON — automation running safely.")
    print("\n" + "-" * 72 + "\n")
    time.sleep(4)

    print("----- TRACE 2 : corrupted device stream (device_fault.pi) -----\n")
    second = compiler.compile_file(
        str(EXAMPLES / "device_fault.pi"), output_dir=str(work), report=print
    )
    print(f"[compiler] ok={second.ok}  threat findings={second.threat_count}")
    print(f"[compiler] artifacts emitted: {artifacts(second) or 'NONE'}")
    for error in second.errors:
        print(f"ERROR: {error.message}")
    led(green=False, red=True)
    print("\nSAFE-FAIL engaged — appliance disengaged, hardware isolated.")
    print("    Compilation blocked before deployment (exit code 2).")

    return 0 if first.ok and not second.ok else 1


if __name__ == "__main__":
    sys.exit(main())
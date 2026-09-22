# SentryPi Quickstart — Project Starting Guide

Everything you need to go from `git clone` to a blinking LED, then to a full
Smart Home automation kit. Hardware pieces and wiring live in
[HARDWARE-GUIDE.md](HARDWARE-GUIDE.md).

---

## 1. Zero-Code Sandbox (no hardware needed)

Start on any machine to feel the pipeline before buying parts:

```bash
git clone https://github.com/ZeroHackOrg/SentryPi.git
cd sentrypi

python3 -m venv venv
source venv/bin/activate
pip install -e .

sentryc --version                      # sentryc 0.2.1 (SentryPi Security Compiler)
sentryc examples/blink.pi              # full pipeline, 4 artifacts emitted
sentryc examples/smart_home.pi         # Smart Home Kit example
sentryc examples/security_test.pi      # firewall demo — refuses to compile
python -m unittest discover -s tests -v   # 90 unit tests
sentryc serve                          # browser playground at :8765
```

> Note: on Debian/Ubuntu with externally-managed Python (PEP 668), use the
> venv above — never `--break-system-packages` unless you know what you're
> doing.

## 2. What Compiling Actually Produces

`examples/blink.pi` → in the current directory:

| Artifact | Purpose |
| :--- | :--- |
| `blink.bin` | hardened execution mapping (`SPI1` magic, bytecode records) |
| `blink.map` | human-readable record-by-record listing |
| `blink.sh` | deployable `#!/bin/bash` sysfs script (no runtime) |
| `blink_driver.py` | high-speed `mmap /dev/gpiomem` Python driver |

Read the map to verify before deploying:

```
$ cat blink.map
[0] LINK     pin=18  value=0  index=0
[1] LINK     pin=0   value=0  index=1
[2] TRIGGER  pin=18  value=1  index=2
[3] DELAY    pin=0   value=500ms index=3
[4] TRIGGER  pin=18  value=0  index=4
...
```

## 3. Project Checklist (before touching hardware)

- [ ] Raspberry Pi 4B or 5 + 5V USB-C PSU + microSD (16GB+) — see HARDWARE-GUIDE § 1
- [ ] Breadboard, LEDs, 220 Ω resistors, jumper wires, PIR / reed switch
- [ ] Raspberry Pi OS (Bookworm) flashed and booted
- [ ] `sudo usermod -aG gpio $USER` then log out/in (for `/dev/gpiomem`)
- [ ] Install SentryPi (step 1 above) on the Pi
- [ ] Wire and test `blink.pi`, then `smart_home.pi` (HARDWARE-GUIDE § 3)

## 4. Hello World on Silicon

```bash
cd sentrypi
sentryc examples/blink.pi                # emit artifacts
sudo bash blink.sh                       # sysfs path — LED blinks twice
sudo python3 blink_driver.py             # /dev/gpiomem path — same result
```

If you see `Hardware Access Denied`, re-login after the `gpio` group change, or
run under `sudo`.

## 5. Signature Gate (CI/CD hardening)

Turn on mandatory Signed sources for your team:

```bash
export SENTRYPI_MASTER_KEY="0xcafebabe42424242"
sentryc sign examples/blink.pi -o signed.pi
sentryc signed.pi                       # Verified.
```

Anyone editing `signed.pi` now hits ` Signature Mismatch` → exit 2.

## 6. Next Steps

- Wire the full kit: [HARDWARE-GUIDE.md](HARDWARE-GUIDE.md)
- Port to ESP32 / STM32 / Arduino & AI: [PORTING-AND-EXTENDING.md](PORTING-AND-EXTENDING.md)
- Enterprise confidentiality & ownership: [ENTERPRISE-DELIVERY.md](ENTERPRISE-DELIVERY.md)
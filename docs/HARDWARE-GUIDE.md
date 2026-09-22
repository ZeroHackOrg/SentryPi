# SentryPi Hardware Guide — Parts, Wiring, Deployment

Physical bring-up for the Raspberry Pi platform, from starter kit to a full
Smart Home automation board.

---

## 1. Required Hardware

### Kit: Blink-Starter (`examples/blink.pi`)

| Part | Spec | Notes |
| :--- | :--- | :--- |
| Raspberry Pi | 4B **or** 5 | officially supported boards |
| microSD card | 16 GB+, Class 10 | Raspberry Pi OS (Bookworm 64-bit) |
| Power supply | 5 V / 3 A USB-C | never power from shady phone chargers |
| Breadboard | 830-point | half-size is fine |
| Jumper wires | male–male, 10+ | |
| LED | 5 mm, any color | 2 for blink |
| Resistor | 220 Ω × 2 | 1 per LED, in series |

### Kit: Smart Home (`examples/smart_home.pi`)

Everything above plus:

| Part | Spec | Used for |
| :--- | :--- | :--- |
| PIR motion sensor | HC-SR501 or equivalent | `MOTION` (pin 23) |
| Reed/magnetic switch | normally-open | `DOOR_SENSOR` (pin 24) |
| Second LED | green | `GARAGE_LIGHT` (pin 22) |
| Resistor | 10 kΩ × 2 | pull-down on sensor signals |

> **0 Ω**, unbraided, or under-spec pull resistors cause floating inputs and
> overcurrent. When in doubt: more resistance, not less — pins source ~16 mA.

---

## 2. Physical → BCM Pin Map (authoritative)

SentryPi uses **physical 40-pin header numbering** in `.pi` source. The BCM
numbers that reach the driver/sysfs:

| Physical pin | BCM GPIO | Common use in examples |
| :--- | :--- | :--- |
| 18 | BCM 24 | LED / output (blink, alarm, smart home) |
| 22 | BCM 25 | garage/utility light |
| 23 | BCM 11 | PIR motion input |
| 24 | BCM 8 | door reed switch input |

 Pins 1, 2, 4, 6, 9, 14, 20, 25, 30, 34, **39** are reserved (power/ground/
boot) and rejected by the firewall.

---

## 3. Bring-Up Steps

### 3.1 OS + permissions

```bash
# 1. Flash Raspberry Pi OS, boot, then:
sudo apt update && sudo apt -y upgrade

# 2. Grant the gpio group access to /dev/gpiomem (also enables sysfs)
sudo usermod -aG gpio $USER
sudo reboot    # re-login required for group membership

# 3. Verify the device node exists
ls -l /dev/gpiomem
# crw-rw---- 1 root gpio ... /dev/gpiomem
```

### 3.2 Install the compiler on the Pi

```bash
sudo apt -y install python3-venv git
git clone https://github.com/ZeroHackOrg/SentryPi.git
cd SentryPi
python3 -m venv venv && source venv/bin/activate
pip install -e .
sentryc --version
```

### 3.3 Blink (validation test)

```text
Physical 18 ──► 220 Ω ──► LED(anode → GPIO, cathode → GND)
```

```bash
sentryc examples/blink.pi
sudo bash blink.sh                 # sysfs path
sudo python3 blink_driver.py       # /dev/gpiomem mmap path
```

### 3.4 Smart Home Kit wiring

| `.pi` alias | Physical pin | Connect to |
| :--- | :--- | :--- |
| `LIVING_LIGHT` | 18 → 220 Ω | LED anode (cathode → GND) |
| `GARAGE_LIGHT` | 22 → 220 Ω | second LED anode (cathode → GND) |
| `MOTION` | 23 | PIR `OUT`; PIR `VCC`→5 V, `GND`→GND |
| `DOOR_SENSOR` | 24 | reed switch one leg; other leg → GND; 10 kΩ to 3V3 as pull | 

```bash
sentryc examples/smart_home.pi
sudo python3 smart_home_driver.py
```

Observe: on motion, `LIVING_LIGHT` turns on; on door open (`LOW`), the garage
light turns on. The `ATOMIC` regions and `DELAY` barriers keep every read →
act transaction race-free and the toggle current safe by construction.

---

## 4. Deploying at the Edge

- **Sysfs script** (`*.sh`) — run under systemd as a oneshot service as the
  `gpio` group user.
- **Driver** (`*_driver.py`) — for latency-sensitive loops; run as a `gpio`
  user, never root-on-the-net.
- **Signed builds** — compile once, sign the artifacts, deploy with a verified
  checksum: see [ENTERPRISE-DELIVERY.md](ENTERPRISE-DELIVERY.md).

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| `Hardware Access Denied` (driver) | user not in `gpio` group | `sudo usermod -aG gpio $USER` + re-login |
| `cat: /sys/class/gpio/...`: Permission denied | sysfs export blocked | run as `gpio` user or `sudo` (script does both) |
| LED never lights | anode/cathode reversed or no resistor | LED long leg → GPIO; add 220 Ω |
| Sensor always reads HIGH/LOW | floating input | add pull-down (10 kΩ to GND) |
| `.pi` won't compile | firewall sees a threat | read the ` COMPILE ERROR` line and fix, never bypass |
| `exit=1` with panic-recovery lines | syntax errors | fix all reported lines, recompile |
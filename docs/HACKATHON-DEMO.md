# 🏆 SentryPi at the Hackathon — "The Human-Centric Smart Home"

**The one-line story judges remember:** *"A lightweight, plain-English
language that compiles smart-home automation straight onto a Raspberry Pi —
and a built-in Safe-Fail firewall that refuses to deploy broken or corrupted
logic before it can ever touch your hardware."*

SentryPi is pitched as **Next-Generation Smart Home Automation & Edge
Computing**: a secure, human-friendly Domain-Specific Language (DSL) and
compiler for automating smart spaces without the complexity of heavy
programming frameworks.

---

## 🎙️ The 3-Minute Oral Pitch Script

> "Judges, smart home automation is fragmented and overly complex. If an
> everyday maker wants to hook a motion sensor to an air conditioner or a
> smart lock, today they have to write messy Python, manage async threads,
> and configure heavy web servers like Flask. That's a massive barrier to
> entry.
>
> "We built **SentryPi** to solve it. It's a lightweight, human-centric
> programming language where you write automation rules in plain English.
> Our compiler parses that text right on the edge — using a Raspberry Pi —
> and generates ultra-fast, direct memory-mapped instructions to toggle
> physical appliances.
>
> "Most importantly, it has an underlying **Safe-Fail Execution Pass** that
> intercepts hardware misconfigurations or broken data streams **before they
> execute** — so your appliances never freeze, crash, or fail. Here's the
> demo."

---

## 📝 The Two Demo Scripts (side-by-side on the table)

### Script 1: `examples/living_room.pi` — the normal automation state

Clean, elegant, and readable — a regular user setting up a smart-home trigger:

```
LINK PIN 18 TO AC_COOLING_SYSTEM AS OUTPUT
LINK PIN 23 TO MOTION_SENSOR AS INPUT

ATOMIC
    IF MOTION_SENSOR IS HIGH THEN
        TRIGGER AC_COOLING_SYSTEM HIGH
        LOG "Motion detected. Adjusting climate matrix safely."
    END
END
```

Compiles clean with **zero firewall findings** and emits four artifacts
(`.bin`, `.map`, `.sh`, `_driver.py`). The `ATOMIC ... END` block guarantees a
**race-free** sensor read — no TOCTOU window.

### Script 2: `examples/device_fault.pi` — the smart Safe-Fail state

When a smart lock or temperature sensor malfunctions, short-circuits, or
receives a massive flood of corrupted noise data:

```
LINK PIN 18 TO SMART_DOOR_LOCK AS OUTPUT
FORCE OVERRIDE SMART_DOOR_LOCK WITH "CORRUPTED_DATA_STREAM_NOISE" * 40000
```

The compile-time **Security Firewall** detects the oversized (1 MB) payload as
a buffer-overflow threat and **refuses to emit any binary**:

```
❌ COMPILE ERROR [Line 2]: Buffer overflow vulnerability detected! String size
   (1000000 bytes) exceeds safe buffer allotment of 256 bytes.
⚠️  Compilation aborted. Physical hardware protected.
```

Exit code is **2** — nothing executes, the appliance stays disengaged. That is
the Safe-Fail promise: broken data streams are intercepted at compile time.

> When comparing to imperative code a newcomer already knows, show the same
> idea with the **malicious_overflow.pi** pattern (`security_test.pi` in the
> kit): `FORCE OVERRIDE BUFFER WITH "A" * 5000` — the firewall blocks it with
> the identical path and exit code.

---

## 💻 The Live Smart Home Edge Engine

Run the real pipeline end-to-end, exactly as a judge would on your table:

```bash
# Install (once)
python3 -m venv .venv && .venv/bin/pip install -e .
export PATH="$PWD/.venv/bin:$PATH"

# Trace 1 — healthy script compiles and deploys
sentryc examples/living_room.pi -o /tmp/hack-build
sudo bash /tmp/hack-build/living_room.sh        # sysfs (slow, safe)

# Trace 2 — corrupted stream is blocked before it deploys
sentryc examples/device_fault.pi -o /tmp/hack-build
echo $?    # 2 — firewall blocked the build; hardware untouched
```

Or run the narrated two-trace table driver (works with or without a Pi, no
simulation — it calls the real compiler):

```bash
sudo python3 examples/hackathon_demo.py
```

It prints both traces, highlights the blocked build, and — when hardware is
present — drives the green/red LEDs described below.

---

## 🎨 The Winning Execution Layout (On the Hackathon Table)

1. **The Visual Rig** — Raspberry Pi 4B on the desk, open, with two LEDs:

   | Indicator | Raspberry Pi wiring | Meaning |
   | :--- | :--- | :--- |
   | 🟢 Green LED | BCM GPIO **18** (physical header pin 12) · 220 Ω | working smart-home appliance (AC / lock / valve) |
   | 🔴 Red LED | BCM GPIO **23** (physical header pin 16) · 220 Ω | system **Safe-Fail lockdown** state |

   > **Pin-numbering note:** the `.pi` language uses **physical 40-pin header
   > positions** (the numbers printed on the header). The compiler translates
   > them to BCM/sysfs numbers in the emitted scripts automatically
   > (physical 18 → BCM 24, physical 23 → BCM 11, physical 12 → BCM 18,
   > physical 16 → BCM 23). The table above gives BCM numbers because the
   > demo narratives and `hackathon_demo.py` use the sysfs convention.

2. **The Live Demo Action**

   - Run `sudo python3 examples/hackathon_demo.py`.
   - **Trace 1:** the compiler builds `living_room.pi`, emits the artifacts,
     executes the sysfs mapping, and **lights the green LED** — appliance
     running.
   - **Trace 2:** four seconds later, the corrupted stream hits
     `device_fault.pi`; the firewall throws the compile error, drops the
     build, **turns off the green LED and switches on the red LED** in front
     of the judges.
   - Talk to the board: point out that *no binary ever reached the hardware
     in Trace 2* — the Safe-Fail gate keeps the physical layer isolated.

---

## 📊 The Universal Domain Pitch Matrix

Pitch the same technology through multiple industry lenses:

| Presentation Angle | Everyday Reality / Pain Point | 🚀 How SentryPi Solves It Natively | 💰 Commercial Value |
| :--- | :--- | :--- | :--- |
| 🚜 Agri-Tech & Drones | Farmers and drone operators don't know C++ — automation stays out of reach. | Plain-English control mapping (`LINK PIN 18 TO WATER_VALVE`). | Cuts training costs; accelerates regional farm automation. |
| 🏠 Next-Gen Smart Homes | Connecting smart components means messy setups that lock or crash when a sensor breaks. | Safe-Fail compilation isolates failing devices without freezing the whole home. | Unmatched uptime guarantees for consumer appliance platforms. |
| 🛡️ Cybersecurity | AI assistants code quickly but skip memory checks, creating buffer vulnerabilities. | Threat analysis is structural and automatic — no human error window. | Security shifted fully into compile-time pipelines. |
| 🤖 AI / ML Integration | Autonomous agents running system commands can be manipulated by injected data. | The compiler verifies data structures pre-deployment as an injection gateway. | A secure execution sandbox for enterprise cloud workloads. |

---

## 🤝 The Open-Source Global Community Call to Action

SentryPi scales beyond an academic exercise into a globally recognized
open-source infrastructure node managed by **ZeroHack.org**.

**For contributors:** expand the context-free grammar (WHILE loops, math
statements), build DevSecOps CI to sanitize `.pi` dependencies, and write
hardware backends to migrate codegen from Raspberry Pi to **ESP32 and Arduino
DIP boards**.

**For partners:** we're seeking industry partnerships, educational pilots, and
venture backing to bring secure, low-overhead programming to schools and
industries across East Africa. ZeroHack licenses enterprise-tier compiler
backends for sensitive environments.

📥 solutions@zerohack.org · 🌐 ZeroHack.org · 📍 Nairobi, Kenya

---

## 📣 Social / Launch Copy (LinkedIn & X)

> Introducing **SentryPi (.pi)** — a human-centric compiler that turns plain
> English into safe edge automation on a Raspberry Pi.
>
> 🏠 Write "IF MOTION_SENSOR IS HIGH THEN TRIGGER AC_COOLING_SYSTEM HIGH" —
> and we compile it straight to memory-mapped GPIO instructions.
>
> 🔒 And when a sensor breaks or a data stream floods in, the built-in
> **Safe-Fail firewall** stops the build *before* it touches your hardware —
> no freezes, no crashes, no fried boards.
>
> Built for makers, farmers, students, and smart-home owners. Open source,
> MIT, under ZeroHack.org. #SentryPi #SmartHome #EdgeComputing #RaspberryPi
> #DSL #OpenSource
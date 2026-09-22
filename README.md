# SentryPi (.pi)

**A security-first Domain-Specific Language and Compiler for Raspberry Pi IoT, smart-home automation, and edge computing.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.2.1-informational.svg)](#)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-A22846.svg)](https://www.raspberrypi.com/)
[![Tests](https://img.shields.io/badge/tests-92%20passing-brightgreen.svg)](https://github.com/ZeroHackOrg/SentryPi/actions)
[![Build](https://github.com/ZeroHackOrg/SentryPi/actions/workflows/ci.yml/badge.svg)](https://github.com/ZeroHackOrg/SentryPi/actions)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

SentryPi is an open-source DSL and compiler that lets users write smart-home and
edge-automation rules in plain, human-readable English and compile them directly
onto Raspberry Pi hardware. The compiler replaces the boilerplate of typical
embedded Python projects (async I/O, networking stacks, sysfs bookkeeping) with a
small deterministic language, while a built-in **static security firewall**
rejects unsafe or corrupted logic at compile time — before any electrical signal
reaches the physical hardware.

Built from scratch by ZeroHack.org. No external dependencies, no framework glue,
90+ unit tests.

---

## Table of Contents

- [The Problem](#the-problem)
- [The Solution](#the-solution)
- [Use Cases](#use-cases)
- [The Gap We Close](#the-gap-we-close)
- [How It Works](#how-it-works)
- [The Language](#the-language)
- [The Security Firewall](#the-security-firewall)
- [Cryptographic Source Signing](#cryptographic-source-signing)
- [Backends and Artifacts](#backends-and-artifacts)
- [Command Line](#command-line)
- [Repository Layout](#repository-layout)
- [Getting Started](#getting-started)
- [Documentation](#documentation)
- [Extending and Porting](#extending-and-porting)
- [Contribute](#contribute)
- [Sponsor SentryPi](#sponsor-sentrypi)
- [Enterprise Model](#enterprise-model)
- [Security](#security)
- [Roadmap](#roadmap)
- [References](#references)
- [Contact](#contact)
- [License](#license)

---

## The Problem

Physical automation — smart homes, agricultural controllers, industrial
sensors, education kits — is held back by the same failures, everywhere:

1. **Automation is fragmented and hard.** Wiring a motion sensor to an air
   conditioner or smart lock normally means async Python, HTTP servers, and
   thread management. Most makers, students, and domain experts never cross
   that barrier.
2. **Hand-written GPIO code is unsafe by default.** Buffer overflows, unsafe
   register writes, overcurrent toggles, and race conditions ship silently.
   A damaged sensor or a corrupted data stream can freeze an appliance, a
   valve, or a vehicle.
3. **There is no supply-chain trust.** Nothing proves who authored the code
   that ends up driving physical machinery — a real liability for
   manufacturers who must now comply with security-by-design regulation
   (for example the EU Cyber Resilience Act).

Existing tools respond after the fact: SAST scanners, firmware emulators, or
binary extractors analyze code *after* it is already written. The failures
they find have typically already shipped.

---

## The Solution

SentryPi moves safety into the **compilation phase**. Users write automation
in a tiny, validated plain-English grammar; a 9-stage pipeline verifies
identity, structure, and safety *before* any code is generated:

- **Safe by construction.** The compiler rejects buffer overflows, reserved-pin
  hijacks, system-component writes, TOCTOU races, and overcurrent toggles with
  the exact line and rule — and emits **zero artifacts** when it does.
- **Edge-native.** A Raspberry Pi compiles text straight into direct,
  memory-mapped GPIO instructions (sysfs or `/dev/gpiomem`) — no servers, no
  frameworks, no interpreter bloat.
- **Auditable supply chain.** Optional HMAC-SHA256 source signing proves each
  program was authored by an authorized developer; tampering is stopped at the
  gate.
- **Zero dependencies.** The entire compiler runs on the Python standard
  library.

---

## Use Cases

| Domain | The everyday reality | What SentryPi provides |
| :--- | :--- | :--- |
| Smart homes | connected components lock or crash when a sensor breaks | safe-fail compilation isolates the faulty device without freezing the home |
| Agri-tech and drones | operators don't know C/C++ and automation stays out of reach | plain-English control mapping (`LINK PIN 18 TO WATER_VALVE`) |
| Education | students learn system design on live hardware | a safe sandbox: dangerous programs are rejected before deployment |
| Edge / AI | agents actuate hardware from model output | data structures are verified pre-deployment; actuators are gated by the firewall |

---

## The Gap We Close

Most IoT devices fail because of complex frameworks and poor input
validation [1, 7]. Where the industry relies on write-first, scan-later
tooling, SentryPi makes development and security a single, unified step:

| | The status quo | The SentryPi framework |
| :--- | :--- | :--- |
| Workflow | write complex Python, Flask, or C, then buy a secondary tool (e.g. a SAST scanner) to find bugs | development and security are unified in one tool |
| Supply chain | no source of truth for who wrote what | mandatory HMAC-SHA256 developer signatures |
| Input handling | manual sanitization, easy to get wrong | native input sanitization, register locks, and pointer analysis |
| Failure mode | an insecure script ships and bugs surface later | the compiler structurally rejects or refuses to emit the executable |

A developer cannot accidentally ship an insecure script: the pipeline either
changes the unsafe form or refuses to emit it [1, 5, 8].

---

## How It Works

```
┌──────────────┐   ┌──────────────┐   ┌───────────────────┐   ┌──────────────────┐
│ .pi source   │──▶│ 1. Lexer     │──▶│ 2. Parser (LL(1)) │──▶│ 3. Semantic      │
│ (plain text) │   │ tokenization │   │ panic-mode recovery│  │ analyzer         │
└──────────────┘   └──────────────┘   └───────────────────┘   └────────┬─────────┘
                                                                        │
                                                       ┌────────────────▼─────────┐
                                                       │ 4. SECURITY FIREWALL     │
                                                       │ overflow / hijack / lock │
                                                       │ TOCTOU / overload        │
                                                       └────────────────┬─────────┘
                                                                        │ (clean)
                              ┌─────────────────────────┬───────────────┘
                              ▼                         ▼
                  ┌──────────────────────┐   ┌──────────────────────┐
                  │ 5. IR (three-address │   │ 6. Optimizer          │
                  │ code) / ATOMIC flatten│  │ redundant-write fold  │
                  └──────────┬───────────┘   └──────────┬───────────┘
                             ▼                          ▼
                  ┌──────────────────────────────────────────────┐
                  │ 7. Code Generator (pluggable backend)         │
                  │ .bin hardened mapping / .map listing / .sh    │
                  │ sysfs script / _driver.py /dev/gpiomem mmap   │
                  └──────────────────────────────────────────────┘
```

Every compile that *fails* the firewall reports the exact line and rule and
**zero artifacts are emitted** — the hardware is untouched.

| Stage | Module | Outcome |
| :--- | :--- | :--- |
| 0 | `crypto.py` | HMAC-SHA256 source verification (`AUTHENTICATE` header) |
| 1 | `lexer.py` | Tokens; rejects identifiers > 32 chars and strings > 256 B |
| 2 | `parser.py` | AST; recursive-descent with panic-mode recovery |
| 3 | `semantic_analyzer.py` | Warnings for unknown / duplicate references |
| 4 | `static_analyzer.py` | Security Firewall; errors block compilation |
| 5 | `ir.py` | Three-address code (`ALLOC_PIN`, `WRITE_BIT`, `BRANCH`, ...) |
| 6 | `optimizer.py` | Redundant-write folding, duplicate-allocation removal |
| 7+ | `target_arm.py` | Code generation (.bin / .map / .sh / _driver.py) |

---

## The Language

A `.pi` file is a list of plain-English statements:

```
statement := LINK  PIN <int> TO <name> [AS OUTPUT|INPUT]   # declare hardware
           | <name> HIGH|LOW                               # alias write
           | TRIGGER <name> HIGH|LOW                       # drive an output
           | LOG <string>                                  # log line
           | DELAY <int> MS                                # scheduling barrier
           | IF <name> [IS] HIGH|LOW THEN ... END          # event branch
           | ATOMIC ... END                                # race-free block
           | AUTHENTICATE WITH "<hex>"                     # signature (line 1)
           | FORCE OVERRIDE <resource> WITH <string> [* <int>]  # blocked by firewall
```

A complete, working example (`examples/living_room.pi`):

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

Compile it:

```
$ sentryc examples/living_room.pi -o build

[SentryPi] Scanning tokens... Success.
[SentryPi] Building Abstract Syntax Tree... Success.
[SentryPi] Running Semantic Analysis... Success.
[SentryPi] Running Static Security Firewall... PASS (0 Threats Detected).
[SentryPi] Generating Intermediate Representation... 8 TAC instructions.
[SentryPi] Optimizing instruction schedule... 8 instructions (0 redundant removed).
[SentryPi] Target backend: Raspberry Pi ARM (BCM2835 / BCM2711 / RP1) (id=arm, boards=Raspberry Pi 4B, Raspberry Pi 5).
[SentryPi] Emitting hardened execution mapping... Created 'build/living_room.bin'
[SentryPi] Writing readable map listing... Created 'build/living_room.map'
[SentryPi] Synthesizing deployable sysfs script... Created 'build/living_room.sh'
[SentryPi] Synthesizing high-speed /dev/gpiomem driver... Created 'build/living_room_driver.py'
[SentryPi] Compilation complete. Safe for deployment.
```

---

## The Security Firewall

The firewall (`static_analyzer.py`) walks the AST and blocks any program that
moves outside safe hardware boundaries:

| Rule | Severity | Trigger |
| :--- | :--- | :--- |
| Reserved-pin hijack | ERROR | `LINK` to `1, 2, 4, 6, 9, 14, 20, 25, 30, 34, 39` |
| Invalid pin | ERROR | pin outside the physical 40-pin header |
| System-component lock | ERROR | `LINK` to `SYSTEM_CLOCK` / `SYSTEM_BUS` |
| Input write | ERROR | writing a payload to an `INPUT` peripheral |
| Buffer overflow | ERROR | `FORCE OVERRIDE` effective size > 256 bytes |
| Lexical bounds | ERROR | identifier > 32 chars, string > 256 bytes |
| TOCTOU race | WARN -> ERROR under `--hard` | `IF` reads a peripheral outside `ATOMIC` |
| Current overload | WARN -> ERROR under `--hard` | > 20 pin toggles without a `DELAY` barrier |

Decision flow:

```
source.pi --> has signature (when a key is set)?
   |-- no / mismatch --> atexit 2 (blocked)
   |-- yes --> lex -> parse --> firewall check
                          |-- error --> atexit 2
                          |-- warn (TOCTOU / overload)
                          |     |-- --hard? --> atexit 2
                          |     |-- default  --> emit
                          |-- clean --> emit
```

A hostile source is rejected with the exact failing line and rule:

```
$ sentryc examples/device_fault.pi

[SentryPi] Running Static Security Firewall...
COMPILE ERROR [Line 7]: Buffer overflow vulnerability detected! String size
   (1080000 bytes) exceeds safe buffer allotment of 256 bytes.
Compilation aborted. Physical hardware protected.
```

Warnings (unknown component, duplicate link/pin) are printed but never block
compilation in default mode. `--hard` upgrades the two concurrency rules above
into hard errors for enterprise strict-mode builds.

---

## Cryptographic Source Signing

SentryPi can require every source to be signed by an authorized developer
before it compiles:

- Supply a master key via `--key <hex|passphrase>` or the
  `SENTRYPI_MASTER_KEY` environment variable.
- `sentryc sign file.pi` prepends `AUTHENTICATE WITH "0x<hmac-sha256>"` and is
  idempotent (it re-signs the payload).
- With a key configured, unsigned or tampered sources are rejected with
  `Signature Mismatch` and exit code 2.
- Without a key, verification is skipped (developer mode), so example sources
  stay portable.

```
$ export SENTRYPI_MASTER_KEY="0xcafebabe42424242"
$ sentryc sign alarm.pi -o signed_alarm.pi
[SentryPi] Signed with HMAC-SHA256: 0x732078172c235c422ed47f4fa9bd2a7958f6aecdbb7e3f546cdd1983541918b8
[SentryPi] AUTHENTICATE header written to 'signed_alarm.pi'.

$ sed 's/HIGH/LOW/' signed_alarm.pi > fake.pi
$ sentryc fake.pi
[SentryPi] Cryptographic Signature Verification... FAIL.
CRITICAL: Signature Mismatch! Firmware modification or script injection
attempt intercepted by ZeroHack Firewall.
```

---

## Backends and Artifacts

Code generation is selected through an in-process registry
(`targets.py`). Each backend declares which artifacts it can produce; the
default `arm` target emits four:

| Artifact | Description |
| :--- | :--- |
| `.bin` | hardened execution mapping (`MAGIC "SPI1"`, opcode records) |
| `.map` | human-readable, record-by-record listing |
| `.sh`  | self-contained `#!/bin/bash` sysfs script (`/sys/class/gpio`, BCM numbering) |
| `_driver.py` | zero-dependency `mmap("/dev/gpiomem")` driver for low-latency deployments |

Select a backend with `SENTRYPI_TARGET`; unknown targets fail with the list of
registered ids:

```
$ SENTRYPI_TARGET=arm sentryc examples/alarm.pi -o build
$ SENTRYPI_TARGET=esp32 sentryc app.pi
KeyError: Unknown architecture target 'esp32'. Registered targets: arm.
```

Physical pins are mapped to BCM GPIO through `PHYSICAL_TO_BCM` (e.g. physical
pin 18 -> BCM 24). `FORCE OVERRIDE` is never synthesized in any backend. The
registry exists so ESP32, STM32, Arduino, and LLVM backends can be added as
licensed plugins without touching the compiler core.

---

## Command Line

```
usage: sentryc [-h] [-o OUTPUT_DIR] [--no-bin] [--no-map] [--no-sh]
               [--no-driver] [--hard] [--key KEY] [--version] source

subcommands:
  sentryc sign <source> [-o OUTPUT] [--key KEY]   attach HMAC signature
  sentryc serve [--host HOST] [--port PORT]        localhost web playground

environment:
  SENTRYPI_MASTER_KEY    master signing key (hex or passphrase)
  SENTRYPI_TARGET        backend target id (default: arm)

exit codes:
  0  compiled successfully
  1  lexical / syntax / I/O error
  2  blocked by Security Firewall or signature verification failure
```

| Flag | Effect |
| :--- | :--- |
| `-o DIR` | output directory for artifacts |
| `--no-bin` / `--no-map` / `--no-sh` / `--no-driver` | skip individual artifacts |
| `--hard` | escalate TOCTOU / overload warnings into errors |
| `--key <hex\|passphrase>` | master signing key (overrides env) |

`sentryc serve` launches a localhost web editor that runs the full pipeline in
a browser — ideal as a teaching tool or a demo centerpiece (containerize it in
production).

---

## Repository Layout

```
sentrypi/
├── .github/workflows/ci.yml      # CI: tests, example compiles, signing gates
├── docs/                         # specifications and guides (see Documentation)
├── examples/
│   ├── blink.pi                  # safe hardware init + DELAY barrier
│   ├── sensor.pi                 # ATOMIC polling of hardware inputs
│   ├── alarm.pi                  # event-driven motion alarm (atomic)
│   ├── deploy.pi                 # alias syntax + atomic conditional deployment
│   ├── smart_home.pi             # full multi-output smart-home kit
│   ├── living_room.pi            # healthy smart-home trace (compiles clean)
│   ├── device_fault.pi           # corrupted-stream trace (blocked, exit 2)
│   ├── hackathon_demo.py         # two-trace table driver (real pipeline)
│   ├── race.pi                   # TOCTOU hazard demo (warns; --hard rejects)
│   ├── strobe.pi                 # overload hazard demo (warns; --hard rejects)
│   └── security_test.pi          # simulated security failure vector
├── src/sentrypi/
│   ├── ast_nodes.py              # AST node definitions
│   ├── lexer.py                  # lexical analyzer + input buffer rules
│   ├── parser.py                 # LL(1) parser with panic-mode recovery
│   ├── semantic_analyzer.py      # symbol table, IO-mode checks
│   ├── static_analyzer.py        # the Security Firewall
│   ├── crypto.py                 # HMAC-SHA256 verifier + signer
│   ├── ir.py                     # three-address code generator
│   ├── optimizer.py              # redundant-write folding
│   ├── target_arm.py             # .bin / .map / .sh / _driver.py codegen
│   ├── targets.py                # backend registry
│   ├── compiler.py               # pipeline orchestration
│   ├── cli.py                    # sentryc entry point
│   └── playground.py             # localhost web editor
├── tests/                        # 92 unit tests
├── SECURITY.md                   # disclosure policy and threat model
├── CONTRIBUTING.md               # contributor guide
├── CHANGELOG.md                  # release history
└── LICENSE                       # MIT (ZeroHack.org)
```

---

## Getting Started

Requires Python 3.9+.

```bash
git clone https://github.com/ZeroHackOrg/SentryPi.git
cd sentrypi
python3 -m venv venv
source venv/bin/activate
pip install -e .            # installs the sentryc binary

sentryc --version           # verify install
sentryc examples/blink.pi   # compile the first program (zero hardware required)
python -m unittest discover -s tests -v   # run the 92-test suite
```

The zero-hardware sandbox workflow, first-run wiring, and a signed-CI gate are
covered in `docs/QUICKSTART.md`. Parts lists and wiring for both starter and
smart-home kits are in `docs/HARDWARE-GUIDE.md`. Every example also runs through
the Web Playground (`sentryc serve`).

---

## Documentation

| Document | Contents |
| :--- | :--- |
| `docs/QUICKSTART.md` | zero-hardware sandbox, first compile, signed CI gate |
| `docs/HACKATHON-DEMO.md` | 3-minute pitch script, LED rig, demo traces, pitch matrix |
| `docs/HARDWARE-GUIDE.md` | parts lists, wiring, deployment |
| `docs/SPEC.md` | grammar, security policy, binary-format specification |
| `docs/ARCHITECTURE.md` | full engine spec: pipeline, crypto, IR, drivers |
| `docs/FAQ.md` | technical FAQ and industry comparison |
| `docs/PORTING-AND-EXTENDING.md` | ESP32 / STM32 / Arduino ports, AI integration |
| `docs/ENTERPRISE-DELIVERY.md` | confidentiality, ownership, licensing |

---

## Extending and Porting

- **New backends:** implement the four `Target` hooks, call `targets.register(...)`,
  then `SENTRYPI_TARGET=<id> sentryc app.pi`. Every port inherits the firewall,
  crypto, and optimizer because those run before codegen.
- **New DSL statements:** one AST node, one parser handler, an optional firewall
  rule, and codegen — the exact recipe is in `docs/PORTING-AND-EXTENDING.md`.
- **Framework integration** (MQTT, Home Assistant, Node-RED): every generated
  driver exposes one stable ABI — `set_pin_mode`, `read_pin`, `write_pin`.
- **On-device AI:** feed `read_pin()` telemetry into a TensorFlow Lite model and
  actuate through `write_pin()`.

---

## Enterprise Model

SentryPi follows a strict **open-core model**: the MIT repository is complete
and cloneable by design; the licensed layer carries the commercial value.

- No hidden code in the public repository — a clone yields a fully working
  open-core compiler.
- Licensed surface: ESP32 / STM32 / Arduino backends, native ARM codegen,
  asymmetric (Ed25519) signing, compliance packs, AI engines, per-device key
  binding, and secure-boot integration.
- Every compiled program can be signed: `sentryc sign` -> HMAC gate at stage 0,
  a signed artifact chain from CI to the device, and key material that is never
  committed.
- Signed license files bind to customer machines, are offline-capable, and do
  not phone home.

Honest engineering note: security-by-hiding is rejected. Protection applies to
licensed value and signed artifacts — never to Python obfuscation.

---

## Contribute

SentryPi is an open-source, community-driven project. Contributors of all
levels are welcome — systems engineers, security researchers, web developers,
and first-time open-source contributors.

- **Good first tasks:** extend the grammar (`ANALOG_READ`, timed loops) in
  `lexer.py` / `parser.py`; add behavioral attack signatures to the firewall
  in `static_analyzer.py`; port `target_arm.py` to ESP32 / Arduino.
- **Bugs and feature requests:** open an issue with a minimal reproduction —
  ideally a `.pi` file that compiles or fails unexpectedly.
- **Design review:** the pipeline, IR, and binary format are documented in
  `docs/ARCHITECTURE.md` and `docs/SPEC.md`; comments and RFCs on the
  `ATOMIC` / firewall semantics are especially welcome.

Setup:

```bash
git clone https://github.com/ZeroHackOrg/SentryPi.git
cd sentrypi
python3 -m venv venv && source venv/bin/activate && pip install -e .
python -m unittest discover -s tests -v
```

See `CONTRIBUTING.md` for the code-of-conduct, commit workflow, and CI gates.

---

## Sponsor SentryPi

SentryPi keeps an MIT open core, but a project like this needs real backing to
grow: hardware for test rigs, CI runners, documentation time, and engineers to
port backends. Sponsorship directly funds the roadmap below.

### What sponsors enable

| Tier | Contribution | What you get |
| :--- | :--- | :--- |
| Community | any amount, one-off or recurring | recognition in the project README and release notes |
| Hardware | Raspberry Pi boards, sensors, ESP32/STM32 kits, oscilloscopes | your logo on the docs site, priority access to hardware-testing streams |
| Engineering | funded maintainer time, CI infrastructure, cloud credits | named roadmap items, advisory role, early preview of enterprise backends |

### Where we are headed

- Network-layer threat signatures, loop / timer constructs, analog input.
- ESP32, STM32, Arduino, and LLVM backends.
- Signed, hardware-bound enterprise builds and compliance packs.

Every tier is managed transparently: funds and hardware go to maintainers,
docs, and CI. Corporate sponsorship, educational pilots, and venture backing
for deployments across schools and industries in East Africa are welcome.

**To sponsor or inquire:** email [solutions@zerohack.org](mailto:solutions@zerohack.org)
or reach the maintainer directly at [geek@zerohack.org](mailto:geek@zerohack.org).

---

## Security

See `SECURITY.md` for the vulnerability-disclosure policy and full threat model.
In short: this project treats the compiler as a firewall. If you can make a
malicious `.pi` file reach the hardware, that is a security bug — please report
it privately per the disclosure procedure in `SECURITY.md`.

---

## Roadmap

- Network-layer threat signatures (port binding, raw sockets).
- Loop / timer constructs and a multi-tasking scheduler.
- Analog input (`ANALOG_READ`) and timing primitives.
- ESP32 and Arduino / LLVM IR backends.
- A registry of known CVE patterns for common IoT stacks.

---

## References

**Research and standards**

1. [Design and Implementation of a Secure Compiler and Virtual Machine for Developing Secure IoT Services](https://www.scribd.com/document/951276142/Design-and-Implementation-of-the-Secure-Compiler-and-Virtual-Machine-for-Developing-Secure-IoT-Services)
2. [Secure Compilation Chains (SIGPLAN blog)](https://blog.sigplan.org/2019/07/01/secure-compilation/)
3. [Static Code Analysis for IoT Security: A Systematic Literature Review](https://www.researchgate.net/publication/392837638_Static_Code_Analysis_for_IoT_Security_A_Systematic_Literature_Review)
4. [A Secure Platform for IoT Devices Based on the ARM Platform Security Architecture](https://www.researchgate.net/publication/339403656_A_Secure_Platform_for_IoT_Devices_based_on_ARM_Platform_Security_Architecture)
5. [A Secure Compiler: Implementation and Verification of Language-Based Security](https://dl.acm.org/doi/full/10.1145/3745019)

**Industry and market**

6. [IoT Security Market Report (Mordor Intelligence)](https://www.mordorintelligence.com/industry-reports/iot-security-market)
7. [IoT Security Market Size (Grand View Research)](https://www.grandviewresearch.com/industry-analysis/internet-of-things-iot-security-market)
8. [IoT Security Market (Roots Analysis)](https://www.rootsanalysis.com/internet-of-things-iot-security-market)
9. [You Need to Secure Your IoT Devices (David Bombal)](https://davidbombal.com/you-need-to-secure-your-iot-devices-in-2026/)

**Tools, resources, and talks**

10. [Static Code Analysis (Oligo Security)](https://www.oligo.security/academy/static-code-analysis)
11. [awesome-iot-and-hardware-security](https://github.com/kayranfatih/awesome-iot-and-hardware-security)
12. [Platform Security Architecture on ARM (talk)](https://www.youtube.com/watch?v=UbHl2GVIk5w)

Cited references appear inline as [1-12]; they are provided for background and
further reading. The claims in this README are backed by this project's own
test suite and documented pipeline (`docs/SPEC.md`, `docs/ARCHITECTURE.md`).

---

## Contact

- Developer: Geoffrey Geek
- GitHub: [ZeroHackOrg](https://github.com/ZeroHackOrg)
- Email: [geek@zerohack.org](mailto:geek@zerohack.org)
- Enterprise inquiries: [solutions@zerohack.org](mailto:solutions@zerohack.org)
- Organization: [ZeroHack.org](https://zerohack.org)

---

## License

MIT. Copyright (c) ZeroHack.org. See [LICENSE](LICENSE).
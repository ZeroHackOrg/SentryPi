# Changelog

All notable changes to SentryPi are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) and uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Full Edge Power & Loop Engine** — Lexer regex refactor; new control-flow grammar:
  - `REPEAT <N> TIMES ... END` (bounded loops with overflow + loop-bound checks)
  - `WHILE <pin> [IS] HIGH|LOW ... END` (TOCTOU-guarded conditional task)
  - `EVERY <N> MS ... END` (cooperative periodic task timer)
  - `ANALOG_READ <pin>` and `LINK ... AS ANALOG` (ADC thermistor / sensor channel sampling)
- **ESP32 & Arduino / LLVM IR Backends** — `target_esp32.py`: lowers verified SentryPi AST to an Arduino sketch (`.ino`) via `PHYSICAL_TO_GPIO` and dumps an illustrative LLVM-style IR report (`.ll`), registered in `targets.py` (`SENTRYPI_TARGET=esp32`).
- **Network-Layer Threat Signatures & CVE Registry** — `threats.py`: static pattern scan for raw sockets, port binds, wildcard listeners, and CVE patterns catalogued against the CWE catalog (CWE-121, CWE-120, CWE-798, CWE-78, CWE-319, CWE-122).
- **Security Audit CLI** — `sentryc audit <source>` runs firewall, threat signatures, and CVE matching without emitting artifacts; `--registry` prints the CWE-aligned CVE pattern registry table.
- **New Examples** — `scheduler.pi`, `sensor_analog.pi`, `net_threat.pi`, and `network_attack.pi`.
- **Hackathon smart-home demo** — `examples/living_room.pi` (healthy
  automation trace, compiles clean) and `examples/device_fault.pi`
  (corrupted-stream trace, Safe-Fail firewall blocks it, exit 2) with the
  single-kit wiring in the README and a narrated two-trace table driver
  (`examples/hackathon_demo.py`) that runs the *real* pipeline.
- **Demo & pitch doc** — `docs/HACKATHON-DEMO.md`: the 3-minute oral pitch
  script, script side-by-sides, 2-LED rig layout with BCM↔physical mapping,
  the universal domain pitch matrix (Agri-Tech / Smart Homes / Cybersecurity
  / AI), community CTA, and launch/social copy.
- Unit tests expanded from 92 to **138** (covering control flow, threats, and ESP32 targets); CI updated.

### Changed
- README rebuilt as a production-grade document: problem/solution framing,
  use-case matrix, "The Gap We Close" status-quo comparison, sponsor tiers,
  and a categorized reference list.
- Emoji removed repo-wide (docs, compiler output, playground, demo driver) in
  favor of clean, professional console and documentation formatting.
- README: human-centric smart-home framing, demo-rig wiring note, backend
  registry (`SENTRYPI_TARGET`) in the CLI reference.

### Fixed
- README no longer triggers GitHub's "Unable to render rich display" fallback
  (legacy Mermaid incompatibility removed); its `<br/>`/emoji node labels were
  replaced with portable ASCII pipeline and decision-flow diagrams.

### Verified
- Full feature pass on a clean checkout: all 92 unit tests, editable install,
  example compilation (`.bin` / `.map` / `.sh` / `_driver.py`), firewall
  rejection (exit 2), panic-mode syntax recovery (exit 1), `--hard`
  escalation, HMAC sign → verify → tamper-detection loop, web playground, and
  `SENTRYPI_TARGET` backend resolution.

## [0.2.1] — 2026

### Added
- **Backend target registry** — `targets.py` makes hardware backends pluggable:
  register a `Target`, select via `SENTRYPI_TARGET`, without touching the
  pipeline. Enables licensed ESP32 / STM32 / Arduino / AI backends.
- **Smart Home Kit example** — `examples/smart_home.pi`: multi-output lighting +
  motion/door automation with `ATOMIC` and `DELAY`, wiring in
  `docs/HARDWARE-GUIDE.md`.
- **Docs** — `docs/QUICKSTART.md` (project starting), `docs/HARDWARE-GUIDE.md`
  (parts + wiring + deployment), `docs/PORTING-AND-EXTENDING.md` (other IoT
  frameworks, DSL extension recipe, AI integration, unlock tiers),
  `docs/ENTERPRISE-DELIVERY.md` (confidentiality, ownership, open-core split).
- Compiler reports the active target backend on every build.
- CI compiles the Smart Home example; unit tests now 90.

### Changed
- Version aligned to 0.2.1 (pyproject + `_version` + docs).

## [0.2.0] — 2026

### Added
- **Cryptographic source signing** — HMAC-SHA256 verifier (`crypto.py`),
  `AUTHENTICATE WITH "0x…"` and `# AUTH_SIG: 0x…` headers,
  `sentryc sign` subcommand, `--key` / `SENTRYPI_MASTER_KEY` gate.
- **Panic-mode syntax recovery** — `parser.errors` collects every syntax error;
  the build reports the full count instead of crashing mid-file.
- **TOCTOU & overload firewall rules** — `ATOMIC ... END` race-free regions,
  `DELAY <ms> MS` scheduling barriers, 20-toggle overload counter;
  `--hard` (enterprise strict mode) escalates these WARN rules to ERROR.
- **High-speed `/dev/gpiomem` backend** — `synthesize_driver()` emits a
  zero-dependency `mmap` GPIO driver (`<name>_driver.py`); new binary opcode
  `OP_DELAY = 6`.
- **Web playground** — `sentryc serve` localhost editor + `/compile` endpoint.
- **Examples** — `race.pi` (TOCTOU demo), `strobe.pi` (overload demo);
  `alarm.pi` / `sensor.pi` / `deploy.pi` wrapped in `ATOMIC`; `blink.pi` gains
  `DELAY`.
- **Docs** — `docs/FAQ.md`, `SECURITY.md`, CHANGELOG (this file); README
  rebuilt with Mermaid pipeline/firewall/signing diagrams and a developer
  manual.

### Changed
- Pipeline is now 9 stages: **crypto → lex → parse → semantic → firewall →
  IR → optimize → codegen** (crypto gate runs before tokenization).
- Parser no longer raises on parse errors (recovery contract); tests updated.
- Static analyzer API: `analyze(program, hard=False)` with rule IDs
  (`RULE_TOCTOU`, `RULE_OVERLOAD`, …).
- Compiler emits a fourth artifact by default: `<name>_driver.py`.

### Fixed
- Unified the high-speed backend device name to the standard `/dev/gpiomem`.
- CLI pluralization bug in the panic-recovery summary line.

## [0.1.0] — 2025 (initial release)

### Added
- Security-first DSL and 7-stage compiler pipeline (`sentryc`).
- Lexer with input-buffer boundary rules; LL(1) recursive-descent parser.
- Security Firewall: reserved-pin hijack, buffer overflow, system-component
  lock, INPUT-write and protected-resource rules.
- TAC IR generator, deterministic optimizer (redundant-write folding),
  ARM/Raspberry Pi codegen (`.bin`, `.map`, `.sh`).
- `alarm.pi`, `sensor.pi`, `deploy.pi`, `blink.pi`, `security_test.pi` examples.
- CI workflow; 52 unit tests; `docs/SPEC.md` and `docs/ARCHITECTURE.md`.
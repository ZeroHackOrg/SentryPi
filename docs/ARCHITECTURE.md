# SentryPi: Architecture Specification & Core Compiler Engine

This document outlines the absolute full-power implementation details of the
SentryPi Compiler (`sentryc`). It details how the engine signs, tokenizes,
parses, secures, optimizes, and synthesizes human-friendly `.pi` scripts into
hardened, exploit-proof machine instructions for the **Raspberry Pi 4B/5 ARM
architecture**.

This repository serves as an open-source technical testbed under **ZeroHack
Labs** and acts as a high-authority lead-generation asset for enterprise
security consulting via **[ZeroHack.org](https://zerohack.org)**.

---

## 1. Complete Compiler Pipeline Architecture

SentryPi reimagines the compilation chain by embedding an active **Static
Security Firewall** between the analysis (Frontend) and synthesis (Backend)
phases, preceded by a **cryptographic integrity gate**, and followed by a
deterministic optimizing backend.

```
[ Source Code File (.pi) ]
│
▼
┌───────────────────────────────┐
│ 0. Crypto Verifier (crypto.py)│  HMAC-SHA256 AUTHENTICATE gate.
└─────────────┬─────────────────┘  Rejects unsigned/tampered source.
              ▼  Verified Source
┌───────────────────────────────┐
│ 1. Lexical Analyzer            │  Enforces max bounds on identifiers/strings.
└─────────────┬─────────────────┘
              ▼  Tokens
┌───────────────────────────────┐
│ 2. Syntax Analyzer             │  LL(1) recursive descent + PANIC-MODE
└─────────────┬─────────────────┘  recovery: reports every syntax error,
              ▼  AST                     never crashes mid-file.
┌───────────────────────────────┐
│ 3. Semantic Analyzer           │  Symbol table, data-type & IO-mode validation.
└─────────────┬─────────────────┘
              ▼  Annotated AST
┌───────────────────────────────┐
│ 4. SECURITY FIREWALL           │   THE USP: drops compilation if threat
└─────────────┬─────────────────┘  vectors are detected. `--hard` escalates
              ▼  Verified Safe AST     TOCTOU → overload to hard errors.
┌───────────────────────────────┐
│ 5. IR Generator                │  AST → Three-Address Code (TAC), flattening
└─────────────┬─────────────────┘  ATOMIC blocks, lowering DELAY, skipping AUTH.
              ▼  TAC Instruction Tree
┌───────────────────────────────┐
│ 6. Code Optimizer              │  Deterministic instruction-level optimization:
└─────────────┬─────────────────┘  redundant writes, duplicate allocation.
              ▼  Optimized IR
┌───────────────────────────────┐
│ 7. Code Generator              │  Maps safe IR to hardware artifacts:
└───────────────────────────────┘  .bin (mapping) · .map (listing) · .sh (sysfs)
                                   · _driver.py (high-speed /dev/gpiomem mmap)
```

Modules map 1:1 to these stages:

| Stage | Module |
| :--- | :--- |
| Signature verification | `src/sentrypi/crypto.py` |
| Lexical analysis | `src/sentrypi/lexer.py` |
| Syntax analysis | `src/sentrypi/parser.py` |
| AST definitions | `src/sentrypi/ast_nodes.py` |
| Semantic analysis | `src/sentrypi/semantic_analyzer.py` |
| Security firewall | `src/sentrypi/static_analyzer.py` |
| TAC IR generation | `src/sentrypi/ir.py` |
| Optimization | `src/sentrypi/optimizer.py` |
| Code generation | `src/sentrypi/target_arm.py` |
| Orchestration | `src/sentrypi/compiler.py` |
| `sentryc` binary | `src/sentrypi/cli.py` |
| Web playground | `src/sentrypi/playground.py` |

---

## 2. Frontend Specifications

### 2.a Regular Expressions & Token Definition (`lexer.py`)

To prevent low-level stack or heap memory exploits, the Lexical Analyzer
implements a strict **Input Buffer Boundary Rule**. Any single token exceeding
its declared bound is flagged as a Buffer Overflow Threat Vector and rejected
immediately at compile time.

| Token | Pattern | Example | Max bound |
| :--- | :--- | :--- | :--- |
| `LINK` | `^LINK\b` | `LINK PIN 18 TO LED AS OUTPUT` | fixed keyword |
| `PIN` | `\bPIN\b` | physical pin connector | 2 bytes |
| `TO` / `AS` | `\b(TO\|AS)\b` | structural connector | 2 bytes |
| `OUTPUT` / `INPUT` | `\b(INPUT\|OUTPUT)\b` | IO mode | fixed keyword |
| `TRIGGER` / `HIGH` / `LOW` | keyword set | digital assignment | fixed keyword |
| `IF` / `THEN` / `END` / `IS` / `ATOMIC` / `DELAY` / `MS` / `AUTHENTICATE` / `WITH` | keyword set | control flow & signing | fixed keyword |
| `IDENT` | `[a-zA-Z_][a-zA-Z0-9_]*` | component alias | `IDENTIFIER_MAX = 32` |
| `INT` | `[0-9]+` | pin number | validated `1..40` |
| `STRING` | `"[^"]*"` | log/authenticate payload | `STRING_MAX_BYTES = 256` |

### 2.b Context-Free Grammar (CFG) (`parser.py`)

SentryPi removes boilerplate by enforcing a clean, deterministic context-free
grammar validated by an **LL(1)** parsing engine with **panic-mode recovery**:
on a parse error the engine synchronizes to the next line boundary or block
`END`, records the failure, and continues — so a file with several bugs reports
them *all* in one compile.

```
Program           -> StatementList
StatementList     -> Statement StatementList | ε
Statement         -> LinkStmt | AssignStmt | TriggerStmt | LogStmt
                   | DelayStmt | IfStmt | AtomicStmt | AuthenticateStmt | ForceStmt
LinkStmt          -> LINK PIN INT TO IDENT [ AS ( OUTPUT | INPUT ) ]
AssignStmt        -> IDENT ( HIGH | LOW )
TriggerStmt       -> TRIGGER IDENT ( HIGH | LOW )
LogStmt           -> LOG STRING
DelayStmt         -> DELAY INT MS
IfStmt            -> IF IDENT [ IS ] ( HIGH | LOW ) THEN StatementList END
AtomicStmt        -> ATOMIC StatementList END
AuthenticateStmt  -> AUTHENTICATE WITH STRING
ForceStmt         -> FORCE OVERRIDE ( IDENT | BUFFER ) WITH STRING [ * INT ]
```

Notes:

- `ForceStmt` exists to simulate attack vectors; it is never emitted safely.
- The `IS` connector inside `IfStmt` is optional (`IF PIR HIGH THEN` ==
  `IF PIR IS HIGH THEN`); both are valid, so existing `.pi` sources keep parsing.
- `AtomicStmt` guarantees that read → act transactions (the `IF` query and the
  resulting writes) are treated as one uninterruptible region by the firewall.

### 2.c Semantic Analysis (`semantic_analyzer.py`)

Builds the symbol table and validates type/IO semantics:

- Warns on references to unknown components.
- Warns on duplicate component links and duplicate pin claims.
- Warns when `AUTHENTICATE` appears anywhere other than line 1.

---

## 3. The Security Firewall (`static_analyzer.py`)

The parser produces an **Abstract Syntax Tree (AST) node array**. Before this
structure reaches the backend, the AST is scanned by the custom security
engine:

```python
class SentrySecurityFirewall:
    RESERVED_SYSTEM_PINS = [1, 2, 4, 6, 9, 14, 20, 25, 30, 34, 39]
    MAX_STRING_BYTES = 256
    MAX_TOGGLES_WITHOUT_DELAY = 20
    HARD_ESCALATION_RULES = {RULE_TOCTOU, RULE_OVERLOAD}

    def analyze(self, program, hard=False):
        ...
```

### Audit rules

| # | Vector | Rule ID | Check | Severity |
| :- | :--- | :- | :--- | :- |
| 1 | Hardware privilege escalation | `RULE_RESERVED_PIN` | `LINK` to a reserved power/ground pin | ERROR |
| 2 | Invalid pin | `RULE_INVALID_PIN` | pin outside physical header `1..40` | ERROR |
| 3 | System component lock | `RULE_SYSTEM_COMPONENT` | `LINK` to `SYSTEM_CLOCK` / `SYSTEM_BUS` | ERROR |
| 4 | Logic manipulation | `RULE_INPUT_WRITE` | write payload to an `INPUT` peripheral | ERROR |
| 5 | Buffer overflow | `RULE_BUFFER_OVERFLOW` | `FORCE OVERRIDE` > 256 effective bytes | ERROR |
| 6 | Protected resource write | `RULE_PROTECTED_RESOURCE` | `FORCE OVERRIDE` of system resources | ERROR |
| 7 | **TOCTOU race** | `RULE_TOCTOU` | `IF` queried outside an `ATOMIC` block | WARN (ERROR in `--hard`) |
| 8 | **Current overload** | `RULE_OVERLOAD` | > 20 toggles with no `DELAY` between | WARN (ERROR in `--hard`) |

`DELAY` is a scheduling barrier: it resets the per-pin toggle counter, so fast
elaborate sequences are legal as long as a delay separates every batch.

`FORCE OVERRIDE` is never lowered to IR — it only ever exists as an
attack-vector candidate on the auditor's desk.

---

## 4. Backend Specifications & Synthesis

### 4.a Intermediate Code Generation (IR, `ir.py`)

Safe code is lowered to a linear **Three-Address Code (TAC)** array, abstracting
high-level constructs away from physical chip layouts via numbered registers
(`t0`, `t1`, …).

**Input (`alarm.pi`):**

```text
LINK PIN 18 TO ALARM AS OUTPUT
ALARM HIGH
```

**Generated TAC:**

```text
ALLOC_PIN  18, OUTPUT, t0
MAP_ALIAS  t0, "ALARM"
WRITE_BIT  t0, 1
```

A conditional block lowers to a `BRANCH reg value → label` plus a `LABEL`
anchor that lands on the first guarded instruction.

New lowering rules:

- `ATOMIC` blocks are **flattened** — their body is spliced into the enclosing
  scope; the keyword has no runtime cost.
- `DELAY 500 MS` lowers to a single `DELAY ms=500` instruction.
- `AUTHENTICATE` is metadata-only and produces **no** instructions.
- `FORCE OVERRIDE` never reaches IR.

### 4.b Code Optimizer (`optimizer.py`)

The optimization engine uses deterministic passes to reduce I/O wear on
physical circuits and shrink the instruction schedule:

- **Redundant bit folding** — consecutive identical `WRITE_BIT` instructions
  are collapsed to one (a double `ALARM HIGH` writes the pin once).
- **Duplicate allocation removal** — repeated `ALLOC_PIN` / `MAP_ALIAS`
  sequences are dropped.
- **Barrier reset** — folding never crosses a `BRANCH` or `DELAY`, and a
  `DELAY` resets the `previous_write` tracker, keeping timed sequences intact.

Removal counts are reported by `sentryc` on every build.

### 4.c Direct Code Generation (`target_arm.py`)

SentryPi synthesizes four artifacts per source.

**`<name>.bin`** — hardened execution mapping (`SPI1` magic):

| Opcode | Mnemonic | pin | value | index |
| :- | :--- | :--- | :--- | :--- |
| 1 | `LINK` | physical pin | `0` OUTPUT / `1` INPUT | — |
| 2 | `TRIGGER` | physical pin | `0` LOW / `1` HIGH | — |
| 3 | `LOG` | — | — | string-table index |
| 4 | `BRANCH` | condition pin | expected level | jump target record |
| 5 | `OVERRIDE` | — | count | — |
| 6 | `DELAY` | — | duration ms | — |

**`<name>.map`** — human-readable record-by-record listing of the same data.

**`<name>.sh`** — a deployable `#!/bin/bash` script that writes directly to
Linux's stable `/sys/class/gpio` user-space interface (BCM numbering), fully
bypassing the overhead of Python or JavaScript interpreters:

```bash
#!/bin/bash
# Compiled securely via SentryPi Framework v0.2.1
if [ ! -d /sys/class/gpio/gpio24 ]; then echo 24 > /sys/class/gpio/export; fi
echo out > /sys/class/gpio/gpio24/direction
echo 1 > /sys/class/gpio/gpio24/value
sleep 0.500
```

### 4.d High-Speed Backend: `<name>_driver.py` (`/dev/gpiomem`)

For latency-critical deployments, SentryPi synthesizes a zero-dependency
Python driver that maps the BCM GPIO peripheral registers through the
standard `/dev/gpiomem` character device shipped with Raspberry Pi OS
(kernel ≥ 4.9):

```
GPIO memory window  (mmap /dev/gpiomem, 4096 bytes, MAP_SHARED)
├── GPFSEL (pin function select)   offset 0x00   → set_pin_mode(pin, mode)
├── GPSET  (set a GPIO high)       offset 0x1C   → write_pin(pin, 1)
├── GPCLR  (set a GPIO low)        offset 0x28   → write_pin(pin, 0)
└── GPLEV  (read GPIO levels)      offset 0x34   → read_pin(pin)
```

All pin numbers are translated from **physical header** positions into **BCM
GPIO** numbers via `PHYSICAL_TO_BCM` (e.g. physical 18 → BCM 24, physical 23 →
BCM 11), matching the `.sh` backend. Register writes use 4-byte `mmap` writes
with `O_SYNC`, eliminating per-pin sysfs round-trips.

Access requirements: the node is exposed to members of the `gpio` group (or
root); the synthesized driver prints `Hardware Access Denied` and exits when
`/dev/gpiomem` cannot be opened, so deployments should run under `sudo` or a
`gpio`-privileged service account. The GPIO register block offsets
(`GPFSEL 0x00` · `GPSET 0x1C` · `GPCLR 0x28` · `GPLEV 0x34`) are relative to
the GPIO controller base and are identical on BCM2835 / BCM2711 (Pi 4B) and
the RP1 GPIO block exposed on Pi 5, keeping the backend portable across the
officially supported boards.

`FORCE OVERRIDE` is never synthesized in any backend — it only ever exists as a
rejected attack vector.

### 4.e Web Playground (`playground.py`)

`sentryc serve` launches a localhost-only HTTP playground (stdlib
`http.server`) with a live editor and a `/compile` endpoint that runs the full
pipeline (crypto → firewall → IR → artifacts) and streams back the exact
`sentryc` stage output. Production deployments are expected to containerize
this endpoint.

---

## 5. Developer Manual

### Development environment setup

```bash
git clone https://github.com/ZeroHackOrg/SentryPi.git
cd sentrypi
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### Full CLI reference

```text
sentryc <source.pi> [-o DIR] [--no-bin] [--no-map] [--no-sh] [--no-driver]
        [--hard] [--key KEY] [--version]
sentryc sign <source.pi> [-o OUT] [--key KEY]
sentryc serve [--host 127.0.0.1] [--port 8765]
```

- `--hard` escalates TOCTOU and current-overload warnings into fatal errors
  (enterprise strict mode).
- `--key` / `SENTRYPI_MASTER_KEY` enable mandatory HMAC signing.
- Exit codes: `0` ok · `1` lexical/syntax/I-O · `2` firewall or crypto reject.

### Compiler diagnostics

```bash
python -m unittest discover -s tests -v
# or, equivalently:
pytest tests/
```

### Enforcement examples

```bash
# relaxed mode: race.pi / strobe.pi WARN but still build
sentryc examples/race.pi
sentryc examples/strobe.pi

# strict mode: both now rejected
sentryc examples/race.pi --hard      # exit 2
sentryc examples/strobe.pi --hard    # exit 2

# mandatory signing gate
export SENTRYPI_MASTER_KEY="0xcafebabe42424242"
sentryc sign examples/alarm.pi -o signed_alarm.pi
sentryc signed_alarm.pi              # Verified
sed s/HIGH/LOW/ signed_alarm.pi > fake.pi
sentryc fake.pi                      #  Signature Mismatch → exit 2
```

### Roadmap for open-source contributors

- **Frontend expansion:** extend `lexer.py` / `parser.py` for analog sensors
  (`ANALOG_READ`) and timed loops.
- **Firewall expansion:** behavioral attack signatures to prevent
  denial-of-service (DoS) logic loops and network-layer threats.
- **Backend migration:** cross-compilation to LLVM IR or native ARM assembly
  for bare-metal microcontrollers (ESP32, Arduino).

---

## 6. B2B Commercial Inquiries & Consulting

`SentryPi` is engineered by **[ZeroHack.org](https://zerohack.org)** to
demonstrate secure product design at the compilation level.

- **Looking for security solutions?** We license custom, enterprise-grade
  compilation layers to hardware manufacturers, medical device developers, and
  automotive firmware vendors.
- **Need an audit?** If your team requires advanced firmware penetration
  testing, architectural vulnerability reviews, or secure development
  pipelines, connect with us directly.

**Contact Core Systems Architect:**
[solutions@zerohack.org](mailto:solutions@zerohack.org) ·
**Digital Defense Lab:** [ZeroHack.org](https://zerohack.org)
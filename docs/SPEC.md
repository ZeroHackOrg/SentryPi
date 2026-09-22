# SentryPi Language & Compiler Specification

This document defines the official grammar, security policy, emitted binary
format, and compilation stages for SentryPi version 0.2.1.

For the full systems-engineering brief (token definitions, IR, optimizer,
sysfs & `/dev/gpiomem` synthesis, contributor guide) see
[ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Source File

- Files use the `.pi` extension (example: `alarm.pi`).
- Line comments start with `#` and extend to the end of the line.
- Identifiers are `[A-Za-z_][A-Za-z0-9_]*`, case-sensitive, max 32 characters.
- Integers are decimal. Pins refer to physical 40-pin header positions.
- Source integrity is protected by an **HMAC-SHA256** signature header (see
  § 6, Cryptographic Signing).

## 2. Grammar (EBNF)

```
program        := { statement }
statement      := link_stmt | assign_stmt | trigger_stmt
                | log_stmt | delay_stmt | if_stmt | atomic_stmt
                | authenticate_stmt | force_stmt

link_stmt      := "LINK" "PIN" INT "TO" IDENT [ "AS" ( "OUTPUT" | "INPUT" ) ]
assign_stmt    := IDENT ( "HIGH" | "LOW" )
trigger_stmt   := "TRIGGER" IDENT ( "HIGH" | "LOW" )
log_stmt       := "LOG" STRING
delay_stmt     := "DELAY" INT "MS"
if_stmt        := "IF" IDENT [ "IS" ] ( "HIGH" | "LOW" ) "THEN" { statement } "END"
atomic_stmt    := "ATOMIC" { statement } "END"
authenticate_stmt := "AUTHENTICATE" "WITH" STRING
force_stmt     := "FORCE" "OVERRIDE" ( IDENT | "BUFFER" ) "WITH" STRING [ "*" INT ]

INT            := digit { digit }
STRING         := '"' { any-char | escape } '"'
```

Notes:

- The `# AUTH_SIG: 0x…` comment header is an accepted alternative to the
  `AUTHENTICATE WITH "0x…"` statement (both occupy line 1).
- `ATOMIC` blocks are flattened into their parent scope by the IR generator;
  they exist to defeat TOCTOU races (see § 4).
- `DELAY 500 MS` inserts a scheduling barrier; it resets the firewall's
  toggle-overload counter and synthesizes `sleep 0.500` / `time.sleep(0.5)`.
- `FORCE OVERRIDE` is an attack-vector simulator; it never compiles to output.
- `IF PIR HIGH THEN` and `IF PIR IS HIGH THEN` are both accepted.
- `IF` and `ATOMIC` blocks nest; every block must be terminated by `END`.

## 3. Compilation Stages

```
crypto → lex → parse → semantic → security firewall → IR (TAC) → optimize → codegen
```

| Stage | Module | Outcome |
| :--- | :--- | :--- |
| Signing | `crypto.py` | HMAC-SHA256 verification (`AUTHENTICATE` header) |
| Lexical | `lexer.py` | Tokens; rejects oversized identifiers/strings |
| Syntax | `parser.py` | AST (LL(1), recursive descent, **panic-mode recovery**) |
| Semantic | `semantic_analyzer.py` | Warnings: unknown / duplicate references |
| Firewall | `static_analyzer.py` | Errors: threat vectors block compilation |
| IR | `ir.py` | Three-address code (`ALLOC_PIN`, `MAP_ALIAS`, `WRITE_BIT`, `BRANCH`, `LABEL`, `LOG`, `DELAY`, `OVERRIDE`) |
| Optimizer | `optimizer.py` | Redundant-write folding, duplicate-allocation removal |
| Codegen | `target_arm.py` | `.bin`, `.map`, `.sh`, `<name>_driver.py` artifacts |

Syntax errors never crash the parser: **panic-mode recovery** skips to the next
statement boundary, collects every error (`parser.errors`), and the pipeline
aborts reporting the full count after scanning the whole file.

## 4. Security Policy (Firewall)

| Rule | Severity | Trigger |
| :--- | :--- | :--- |
| Reserved pin hijack | ERROR | `LINK` to `RESERVED_SYSTEM_PINS = {1,2,4,6,9,14,20,25,30,34,39}` |
| Invalid pin | ERROR | pin outside physical header `1..40` |
| System component lock | ERROR | `LINK` to `SYSTEM_CLOCK` / `SYSTEM_BUS` |
| INPUT write | ERROR | write to a pin declared `INPUT` |
| Buffer overflow | ERROR | `FORCE OVERRIDE` string expansion > 256 bytes |
| Protected resource write | ERROR | `FORCE OVERRIDE` of `SYSTEM_CLOCK` / `SYSTEM_BUS` / `KERNEL_REGISTERS` |
| Lexical bounds | ERROR | identifier > 32 chars, string > 256 bytes (rejected at scan) |
| **TOCTOU race** | WARN → ERROR in `--hard` | `IF` queries a peripheral outside an `ATOMIC` block |
| **Current overload** | WARN → ERROR in `--hard` | > 20 pin toggles without a `DELAY` barrier |

Warnings never block compilation in default mode. `--hard` (enterprise strict
mode) escalates the two concurrency/safety rules above into hard errors.

## 5. Emitted Artifacts

### 5.1 `<name>.bin` — hardened execution mapping

```
Offset   Size           Field
0        4              MAGIC "SPI1"
4        4              u32 record_count
8        8 * n          records (n = record_count)
...      4              u32 string_count
...      var            string table
```

Record layout: `struct.pack("<BBHI", opcode, pin, value, index)`.

| Opcode | pin | value | index |
| :- | :--- | :--- | :--- |
| 1 LINK | physical pin | `0` OUTPUT / `1` INPUT | — |
| 2 TRIGGER | physical pin | `0` LOW / `1` HIGH | — |
| 3 LOG | — | — | string-table index |
| 4 BRANCH | condition pin | expected level | target record (first guarded instruction) |
| 5 OVERRIDE | — | count | — |
| 6 DELAY | — | duration in ms | — |

### 5.2 `<name>.map` — human-readable listing

Renders `[idx] OP pin=… value=… index=…` for every record
(e.g. `[0] DELAY pin=0  value=500ms`).

### 5.3 `<name>.sh` — deployable sysfs script

Self-contained `#!/bin/bash` script targeting `/sys/class/gpio` with BCM GPIO
numbering. `DELAY` becomes `sleep <s>`; `FORCE OVERRIDE` is never synthesized.

### 5.4 `<name>_driver.py` — high-speed `/dev/gpiomem` driver

A zero-dependency Python driver that `mmap`s the Raspberry Pi GPIO peripheral
registers via the standard `/dev/gpiomem` character device, bypassing sysfs
round-trips for low-latency deployments. Requires `gpio` group membership or
root (see ARCHITECTURE.md § 4.d).

## 6. Cryptographic Signing

SentryPi can require that every `.pi` source be cryptographically signed before
it is compiled:

- A master key is supplied via `--key <hex|passphrase>` or the
  `SENTRYPI_MASTER_KEY` environment variable.
- `sentryc sign <file.pi> [--key] [-o out]` prepends
  `AUTHENTICATE WITH "0x<hmac-sha256>"` and is idempotent (it re-signs the
  payload after the header).
- When a key is configured, compilation **rejects** unsigned or tampered
  sources (`Signature Mismatch!` → exit 2). Without a key, signing is skipped
  (developer mode) so examples stay portable.

## 7. Command Line

```
usage: sentryc [-h] [-o OUTPUT_DIR] [--no-bin] [--no-map] [--no-sh]
               [--no-driver] [--hard] [--key KEY] [--version] source

subcommands:
  sentryc sign <source> [-o OUTPUT] [--key KEY]   attach HMAC signature
  sentryc serve [--host HOST] [--port PORT]        localhost web playground

environment:
  SENTRYPI_MASTER_KEY    master signing key (hex or passphrase)

exit codes:
  0  compiled successfully
  1  lexical / syntax / I/O error (threat vector rejected at scan)
  2  blocked by Security Firewall or cryptographic verification failure
```

## 8. Roadmap

- Network-layer threat signatures (port binding, raw sockets).
- Loop / timer constructs and multi-tasking scheduler.
- Analog input (`ANALOG_READ`) and timing primitives.
- Backends for ESP32 and Arduino / LLVM IR (retarget `target_arm.py`).
- Registry of known CVE patterns for common IoT stacks.
# SentryPi: Technical FAQ & Comparison Matrix

Answers to the questions developers, investors, and B2B clients ask when
evaluating SentryPi against standard IoT ecosystems. Every statement here is
verifiable against this repository.

---

## The Final Frontier: SentryPi vs. The Industry Status Quo

| Question / Feature | Standard Python Scripting (GPIO Zero, RPi.GPIO) | Traditional SAST Scanners (SonarQube, Snyk) |  SentryPi Enterprise |
|---|---|---|---|
| What exactly IS it? | A high-level runtime code library used to toggle pins. | An external scanning software that reads text to find bugs. | A standalone compiler engine and custom programming language. |
| When does security happen? | Never. Security depends entirely on the developer writing good logic. | Post-Development. Scans code after it is written, but before it runs. | At Compile-Time. Security is structurally embedded into the build phase. |
| What happens if a threat is found? | The code runs anyway, leading to crashes, memory corruption, or device hijack. | It flags an alert or warning inside a log file that developers often ignore. | The compiler crashes. It completely refuses to generate a binary (`exit 2`). |
| How does it touch the hardware? | Via slow, file-based Linux OS abstraction layers (sysfs). | It doesn't touch hardware; it only scans text software files. | Via direct physical memory mapping (`mmap /dev/gpiomem`) — no sysfs round-trips. |
| Is code integrity verified? | No. Anyone with system access can swap scripts or inject malicious lines. | No. It only scans for logical bugs, not structural file tampering. | Yes. Enforces HMAC-SHA256 cryptographic signatures at line 1. |
| Target Audience | Beginners, hobbyists, and rapid software prototypers. | Corporate software DevOps pipelines and security compliance auditors. | B2B hardware manufacturers, critical infrastructure, tech students. |

---

## The 3 Biggest Myths, Busted

### 1. "Is SentryPi just another Python library?"

**No.** Python libraries run inside an interpreter while the device is running,
consuming RAM and processing power. SentryPi is a complete **compilation
pipeline**: it reads human-friendly language constructs, processes them through
a custom static security firewall, and directly outputs hardened, standalone
drivers (`.sh` + `_driver.py`) with no runtime framework.

### 2. "Why use SentryPi if I already use a scanner like Snyk?"

Traditional scanners are **advisory** — they tell you a problem exists but do
nothing to stop an engineer from pushing unsafe code to a physical device.
SentryPi is an **active gatekeeper**: if the code is unsafe it *physically
cannot compile*, rendering the exploit completely un-deployable.

### 3. "Does this replace the Raspberry Pi OS?"

**No.** It runs on top of standard Linux distributions (like Raspberry Pi OS).
Instead of forcing developers to write complex, insecure C or bash to
manipulate pins, SentryPi is a secure, human-friendly translation layer that
converts simple code into low-level hardware optimizations.

---

## The Compile-Time Firewall

### What does the firewall actually block?

Hard errors — the build **refuses to emit a binary** (`exit 2`):

| Rule | Trigger |
| :--- | :--- |
| Reserved pin hijack | `LINK` to a reserved power/ground pin |
| Invalid pin | pin outside the physical 40-pin header |
| System component lock | `LINK` to `SYSTEM_CLOCK` / `SYSTEM_BUS` |
| Logic manipulation | writing a payload to an `INPUT` peripheral |
| Memory injection | `FORCE OVERRIDE` effective size > 256 bytes |
| Lexical bounds | identifier > 32 chars, string > 256 bytes |
| **Supply-chain tampering** | source unsigned or signature mismatch |

Warnings (escalated to errors with `--hard` / enterprise strict mode):

| Rule | Trigger |
| :--- | :--- |
| **TOCTOU race** | `IF` queries a peripheral outside an `ATOMIC` block |
| **Current overload** | > 20 pin toggles with no `DELAY` barrier |

### What is an `ATOMIC` block for?

It signals an uninterruptible read → act transaction. Wrapping a peripheral
`IF` query in `ATOMIC ... END` tells the firewall the branch decision and its
resulting writes are one region — the classic time-of-check/time-of-use race is
eliminated structurally. The keyword has **zero runtime cost**: the IR
generator flattens the block into its parent scope.

### Why is `DELAY 500 MS` part of the language?

Short on-purpose: it is a **scheduling barrier**. It resets the per-pin
toggle-overload counter (preventing a 20+ toggle burst that could overcurrent a
pin), blocks the optimizer from folding writes across it, and lowers to
`sleep 0.500` in bash / `time.sleep(0.5)` in the driver.

---

## Cryptographic Integrity

### Is the signature "asymmetric"?

No — SentryPi uses **HMAC-SHA256, a symmetric keyed MAC**: the same master key
signs and verifies. That is deliberate: one `SENTRYPI_MASTER_KEY` protects an
entire CI/CD pipeline with `sentryc sign`, and verification is extremely fast.
For deployments that require per-supplier asymmetric signatures (Ed25519 /
X.509), that is offered under **ZeroHack Custom Integration**.

### What happens when a key is configured?

- `sentryc sign file.pi` prepends `AUTHENTICATE WITH "0x<hmac-sha256>"`.
- Compiling signed code with the same key → `Verified`.
- Compiling unsigned or modified code → ` Signature Mismatch` → `exit 2`.
- With **no** key in the environment, signing is skipped (developer mode) so
  examples remain portable.

### Why is it a "compile-time" integrity gate?

The check runs as **stage 0 of the pipeline**, before tokenization. An attacker
cannot even reach the lexer without a valid signature — the firmware injection
never becomes a binary.

---

## The High-Speed Backend (`/dev/gpiomem`)

### How does the driver avoid slow sysfs file I/O?

The `_driver.py` artifact `mmap`s the GPIO controller's register window
directly through the standard `/dev/gpiomem` character device (shipped with the
Raspberry Pi kernel):

```
GPIO window  (mmap /dev/gpiomem, 4096 B, O_SYNC, MAP_SHARED)
├── GPFSEL  0x00   → set_pin_mode(pin, mode)
├── GPSET   0x1C   → write_pin(pin, 1)
├── GPCLR   0x28   → write_pin(pin, 0)
└── GPLEV   0x34   → read_pin(pin)
```

Instead of one sysfs round-trip per operation, pin writes are single 4-byte
register stores. Physical header pins are translated to BCM GPIO via
`PHYSICAL_TO_BCM` (e.g. physical 18 → BCM 24, physical 23 → BCM 11), matching
the `.sh` backend.

### What does the device require?

- Raspberry Pi OS (kernel ≥ 4.9; officially supported: Pi 4B and Pi 5).
- `gpio` group membership or root — the driver prints `Hardware Access Denied`
  and exits cleanly otherwise.
- The register offsets are relative to the GPIO controller base and are
  identical on BCM2835 / BCM2711 / RP1, keeping the backend portable.

### Does the `FORCE OVERRIDE` attack vector ever reach a device?

Never. It is an attacker-simulation construct that is **rejected by the
firewall**; no backend (`bin`, `map`, `sh`, `driver`) ever synthesizes it.

---

## Verified CLI Transcript

Reproduced from a real terminal against this repository:

```
$ export SENTRYPI_MASTER_KEY="0xcafebabe42424242"

# 1. Sign a source file
$ sentryc sign alarm.pi -o signed_alarm.pi
[SentryPi] Signed with HMAC-SHA256: 0xfba4f2c224ed929dfab5ed45f481c04fe21d34cf8e820302c5f6b7a4876552ff
[SentryPi] AUTHENTICATE header written to 'signed_alarm.pi'.
 Compile with the same key to verify source integrity.

# 2. Verified sources compile (exit 0)
$ sentryc signed_alarm.pi
[SentryPi] Cryptographic Signature Verification... Verified.
...

# 3. A single tampered byte is stopped (exit 2)
$ sed -i 's/HIGH/LOW/' signed_alarm.pi
$ sentryc signed_alarm.pi
[SentryPi] Cryptographic Signature Verification... FAIL.
  CRITICAL WARNING: Signature Mismatch! Firmware modification or script
   injection attempt intercepted by ZeroHack Firewall.        (exit 2)

# 4. Unsigned source under a configured key is stopped (exit 2)
$ sentryc unsigned_alarm.pi
[SentryPi] Cryptographic Signature Verification... FAIL.
  COMPILE CRASH: Unsigned Source Code. SentryPi compiler requires verified
   developer cryptographic signatures (AUTHENTICATE WITH "0x…").   (exit 2)
```

**Enterprise strict mode (`--hard`)**, no key configured:

```
$ sentryc race.pi                  # warns, still builds  (exit 0)
  [Line 7]: Potential TOCTOU race: IF queries peripheral 'PIR' outside an
              atomic hardware block. Wrap it in ATOMIC ... END.

$ sentryc race.pi --hard           # now a hard error     (exit 2)
[SentryPi] Running Static Security Firewall...
 COMPILE ERROR [Line 7]: Potential TOCTOU race: IF queries peripheral 'PIR'
   outside an atomic hardware block. Wrap it in ATOMIC ... END.
  Compilation aborted. Physical hardware protected.      (exit 2)
```

---

## Roadmap

Shipped in this release:

- Panic-mode syntax recovery (every error reported, never a mid-file crash).
- HMAC-SHA256 gate + `sentryc sign` / `sentryc serve`.
- TOCTOU + current-overload firewall rules, `ATOMIC` / `DELAY` grammar.
- `/dev/gpiomem` mmap driver backend.
- Localhost web playground.

Commercial (ZeroHack Custom Integration — not yet in the open repo):

- True asymmetric signatures (Ed25519) and certificate-based key management.
- Direct ARM / native register code generation and target ports
  (ESP32, STM32, Arduino).
- Custom memory-limit configuration and compliance documentation packs.

---

See also: [docs/SPEC.md](SPEC.md) · [docs/ARCHITECTURE.md](ARCHITECTURE.md)
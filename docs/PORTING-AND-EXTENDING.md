# SentryPi Porting & Extending — Other IoT Frameworks + AI

How to grow SentryPi beyond the Raspberry Pi core: new DSL statements, new
hardware backends (ESP32, STM32, Arduino), framework integrations (MQTT,
Home Assistant, Node-RED), on-device AI, and the Full-Power unlock tiers.

The compiler core is deliberately split so **0 % of the pipeline changes**
when you add a backend or a statement:

```
lexer → parser → semantic → firewall → IR (TAC) → optimize → Target(registry)
                                                        └─ arm (default) 
                                                        └─ your target (plugin)
```

---

## 1. The Backend Registry (`targets.py`)

Every hardware platform is a registered `Target` with a tiny contract:

```python
from sentrypi import targets
from sentrypi.targets import Target

esp32 = Target(
    id="esp32",
    name="ESP32 (Xtensa LX6 / LX7)",
    boards=("ESP32", "ESP32-S3"),
    emit=lambda tac: b"",            # leave None to declare "not supported"
    emit_map=my_emit_map,
    synthesize_bash=my_c_synth,      # your C source instead of bash
    synthesize_driver=my_flash_synth,# esptool flash recipe
    emits_bin=False,                 # capability flags — artifacts skipped
    emits_map=True,
    emits_sh=True,                   # .sh slot repurposed for C source
    emits_driver=True,
)
targets.register(esp32)              # id must be unique & non-empty
```

Select at compile time — no core edits:

```bash
SENTRYPI_TARGET=esp32 sentryc my_script.pi -o build/
```

| Feature | Contact in a target |
| :--- | :--- |
| Machine mapping | `emit(tac)` → bytes for `.bin` |
| Readable listing | `emit_map(tac)` → text for `.map` |
| Deployable source | `synthesize_bash(program)` → sh/C/arduino.ino |
| Runtime driver | `synthesize_driver(program)` → flash script |
| Capabilities | `emits_bin|map|sh|driver` booleans |

The firewall, crypto gate, and optimizer run **before** any target is invoked,
so every backend inherits the same security guarantees.

### Quick port recipe

1. **ARM-style (trusted MCU):** reuse `arm`'s shape — write `emit`/`emit_map`
   against a small opcode set, map physical pins to your MCU's ports.
2. **MCU (ESP32/STM32/Arduino):** set `emits_bin=False`; emit **C or .ino**
   source from `synthesize_bash`, and a `esptool.py`/`st-flash` recipe from
   `synthesize_driver`. Provide board-specific pin routing in `target.metadata`.
3. **Register before compiling** by installing an enterprise pack that calls
   `targets.register(...)` at import time.

---

## 2. Extending the Language (new statements)

Template for adding a statement — touches one AST node, one parser handler,
and optional firewall/IR/codegen support:

| Where | What to edit | Example |
| :--- | :--- | :--- |
| `lexer.py` | add the keyword to the keyword set | `BUZZ` |
| `ast_nodes.py` | `@dataclass Buzz(line)` | `Buzz(ms=200, line=n)` |
| `parser.py` | handler + dispatch in `parse_statement` | `BUZZ <int> MS` |
| `semantic_analyzer.py` | (optional) reference checks | require a linked output |
| `static_analyzer.py` | (optional) firewall rule on the new node | never `FORCE` over `BUZZ` |
| `ir.py` | lower to a `BUZZ ms=…` TAC op | |
| `optimizer.py` | barrier/label handling if data-related | |
| `target_arm.py` / your `Target` | codegen for the new op | `paplay`/GPIO square wave |

Each new statement ships with:
- a lexer/parser unit test,
- a firewall test (safe form compiles, malicious form is rejected),
- a codegen test asserting the artifact contains the lowered form.

---

## 3. Framework Integrations (MQTT · Home Assistant · Node-RED)

SentryPi compiles to deterministic scripts or register drivers — plug them into
any orchestrator:

- **MQTT bridge** — run `smart_home_driver.py` as the actuator module; a thin
  bridge publishes `read_pin()` telemetry to `sentrypi/{unit}/{pin}` and
  consumes `set` commands that call `write_pin()`. Sign the message payload
  with the same master key pattern as `sentryc sign` so an MQTT broker can
  verify actuators.
- **Home Assistant** — `*.sh` works as a shell command step; `_driver.py` works
  behind a REST/`mqtt` switch. Because outputs are deterministic and
  firewall-cleared, automations behave identically every boot.
- **Node-RED** — call the compiled script as a subprocess node; the `bin`
  mapping is a stable, versioned artifact you can checksum and roll back.

The stability contract that makes integrations safe: **`set_pin_mode`,
`read_pin`, `write_pin` are the same three-function ABI in every generated
driver.**

---

## 4. AI Integration

### 4.1 On-device inference loop (today, no DSL changes)

The generated driver IS the sensor/actuator API. Feed `read_pin()` streams into
a local model (TensorFlow Lite) and drive `write_pin()`:

```python
# ai_guard.py — runs beside smart_home_driver.py
from smart_home_driver import read_pin, write_pin, set_pin_mode
import tflite_runtime.interpreter as tflite

model = tflite.Interpreter(model_path="occupancy.tflite")
model.allocate_tensors()

# read telemetry → infer → actuate through the same safe ABI
feat = [read_pin(8), read_pin(11)]          # door, motion
model.set_tensor(inp, [[feat]])
model.invoke()
if model.get_tensor(out)[0][0] > 0.5:
    write_pin(25, 1)                        # garage light
```

Telemetry is bounded to firewall-cleared pins, and your model cannot issue an
unsafe write — the compiler already proved the program deployable.

### 4.2 Proposed DSL extension (frontend roadmap)

Future grammar for native AI control:

```
AI GUARD ENGINE FROM "occupancy.tflite" WITH SENSOR MOTION, DOOR_SENSOR
IF MOTION HIGH THEN
    CALL GUARD WITH "presence"
    TRIGGER LIVING_LIGHT HIGH
END
```

This maps onto the same registry/firewall pipeline: `AI` becomes a statement,
the engine reference a string asset checked for size bounds, and codegen emits
the TFLite call from § 4.1. Enterprise packs may implement this without
touching the open core (a `Target`-style plugin + parser extension callback).

### 4.3 Cloud decisioning with signed payloads

Sensors → MQTT (signed) → cloud model → actuator commands → `write_pin()`.
Artifacts stay verified end-to-end: source signed at build, payloads signed at
runtime, devices refuse unsigned frames.

---

## 5. Full-Power Unlock Tiers (Smart Home & beyond)

| Tier | Audience | Includes | How it's unlocked |
| :--- | :--- | :--- | :--- |
| **Community Core** | makers, students | RPi 4B/5 backend, sysfs + `/dev/gpiomem` drivers, firewall, signing | open MIT repo |
| **SentryPi Enterprise SDK** | hardware manufacturers | all Community features + license-bound packs, custom memory limits, compliance docs, SLA | licensed package, code-signed, private index |
| **ZeroHack Custom Integration** | defense, medical, grid | ESP32/STM32/Arduino backends, asymmetric signing, bespoke DSL, AI engines, on-site audits | bespoke delivery, NDA |

"Full Power" = licensed tier activation, not code hidden in the public repo.
The open core stays complete and MIT; the enterprise value lives in the
licensed layer and services. See [ENTERPRISE-DELIVERY.md](ENTERPRISE-DELIVERY.md).
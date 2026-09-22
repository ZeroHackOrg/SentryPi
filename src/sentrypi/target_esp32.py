"""ESP32 / Arduino backend.

``synthesize_ino`` lowers a verified SentryPi AST to an Arduino sketch for
Espressif ESP32 (e.g. DEVKIT v1, WROOM-32). The DSL's physical pin numbers map
through ``PHYSICAL_TO_GPIO``, an example wiring table for the DevKit boards.

``synthesize_llvm`` emits an illustrative LLVM-style IR dump of the same
lowering. It is documentation-level output (no machine code is generated);
it exists so the frontend can be validated against arbitrary downstream
backends without tying the compiler to a specific toolchain.
"""

from ._version import VERSION
from .ast_nodes import (
    AnalogRead,
    Assign,
    AtomicBlock,
    Authenticate,
    Delay,
    EveryBlock,
    ForceOverride,
    IfBlock,
    LinkPin,
    Log,
    RepeatBlock,
    Trigger,
    WhileBlock,
)

# Representative wiring table for ESP32 DevKit V1 / WROOM-32.
# Maps SentryPi physical pin numbers to ESP32 GPIO numbers.
PHYSICAL_TO_GPIO = {
    6: 34, 7: 25, 8: 33, 10: 32, 11: 26, 12: 27, 13: 14,
    15: 13, 16: 12, 18: 4, 19: 0, 21: 5, 22: 18, 23: 19,
    24: 21, 26: 22, 28: 23, 31: 15, 32: 2, 33: 3, 35: 16,
    36: 17,
}

MODE_ATTR = {"OUTPUT": "OUTPUT", "INPUT": "INPUT_PULLUP", "ANALOG": "INPUT"}
VALUE_ATTR = {"LOW": "LOW", "HIGH": "HIGH"}


def _gpio(pin):
    return PHYSICAL_TO_GPIO.get(pin, pin)


def synthesize_ino(program):
    links = {}
    for statement in program.statements:
        if isinstance(statement, LinkPin):
            links[statement.target] = (
                _gpio(statement.pin),
                statement.mode or "OUTPUT",
            )

    variables = []
    setup_lines = ["  Serial.begin(115200);", "  analogReadResolution(12);"]
    for target, (gpio, mode) in sorted(links.items(), key=lambda item: item[1][0]):
        arduino_mode = MODE_ATTR.get(mode, "INPUT")
        variables.append(f"const int PIN_{target} = {gpio};")
        setup_lines.append(f"  pinMode(PIN_{target}, {arduino_mode});")

    lines = [
        "// Compiled securely via SentryPi Framework v" + VERSION,
        "// Target: Espressif ESP32 (Arduino core).",
        "// Physical pins were verified and mapped through PHYSICAL_TO_GPIO.",
        "",
    ]
    lines.extend(variables)
    lines.append("")
    lines.append("void setup() {")
    lines.extend(setup_lines)
    lines.append("}")

    def walk(statements, indent):
        prefix = "  " * indent
        for statement in statements:
            if isinstance(statement, LinkPin):
                continue
            if isinstance(statement, (Assign, Trigger)):
                gpio, _ = links.get(statement.target, (0, "OUTPUT"))
                lines.append(
                    f"{prefix}digitalWrite(PIN_{statement.target}, "
                    f"{VALUE_ATTR[statement.value]});"
                )
            elif isinstance(statement, Log):
                lines.append(f'{prefix}Serial.println("{statement.message}");')
            elif isinstance(statement, Delay):
                lines.append(f"{prefix}delay({statement.ms});")
            elif isinstance(statement, AtomicBlock):
                lines.append(f"{prefix}// atomic hardware block (single-threaded on ESP32)")
                walk(statement.body, indent)
            elif isinstance(statement, IfBlock):
                lines.append(
                    f"{prefix}if (digitalRead(PIN_{statement.condition}) == "
                    f"{VALUE_ATTR[statement.state]}) {{"
                )
                walk(statement.body, indent + 1)
                lines.append(f"{prefix}}}")
            elif isinstance(statement, RepeatBlock):
                lines.append(
                    f'{prefix}for (int __iter = 0; __iter < {statement.count}; __iter++) {{'
                )
                walk(statement.body, indent + 1)
                lines.append(f"{prefix}}}")
            elif isinstance(statement, WhileBlock):
                lines.append(
                    f"{prefix}while (digitalRead(PIN_{statement.condition}) == "
                    f"{VALUE_ATTR[statement.state]}) {{"
                )
                walk(statement.body, indent + 1)
                lines.append(f"{prefix}}}")
            elif isinstance(statement, EveryBlock):
                lines.append(f"{prefix}while (true) {{")
                walk(statement.body, indent + 1)
                lines.append(f"{prefix}  delay({statement.ms});")
                lines.append(f"{prefix}}}")
            elif isinstance(statement, AnalogRead):
                lines.append(
                    f"{prefix}analogRead(PIN_{statement.target}); "
                    f"// ADC channel on GPIO {links.get(statement.target, (0,))[0]}"
                )
            elif isinstance(statement, Authenticate):
                continue
            elif isinstance(statement, ForceOverride):
                lines.append(
                    f"{prefix}// rejected at compile time: FORCE OVERRIDE is never synthesized"
                )

    lines.append("")
    lines.append("void loop() {")
    walk(program.statements, 1)
    lines.append("}")
    return "\n".join(lines) + "\n"


def synthesize_llvm(program):
    links = {}
    for statement in program.statements:
        if isinstance(statement, LinkPin):
            links[statement.target] = (_gpio(statement.pin), statement.mode or "OUTPUT")

    strings = []

    def intern(message):
        if message not in strings:
            strings.append(message)
        return strings.index(message)

    lines = [
        "; SentryPi LLVM-style backend report (illustrative lowering).",
        "; Module: verified SentryPi AST -> typed SSA-ish pseudo-IR.",
        "",
        'source_filename = "sentrypi-program"',
        "",
        "declare void @llvm.sentry.gpio.link(i32, i8)",
        "declare void @llvm.sentry.gpio.write(i32, i1)",
        "declare i1 @llvm.sentry.gpio.read(i32)",
        "declare void @llvm.sentry.log(i8*)",
        "declare void @llvm.sentry.timer.yield(i32)",
        "declare void @llvm.sentry.repeat.begin(i32)",
        "declare i32 @llvm.sentry.analog.read(i32)",
        "",
        "define void @sentry_main() #0 {",
        "entry:",
    ]

    block = 0

    def block_label():
        nonlocal block
        label = f"bb.{block}"
        block += 1
        return label

    def walk(statements, indent):
        prefix = "  " * indent
        for statement in statements:
            if isinstance(statement, LinkPin):
                gpio, mode = links[statement.target]
                attr = 0 if mode == "OUTPUT" else 2 if mode == "ANALOG" else 1
                lines.append(
                    f"{prefix}%reg.{statement.target} = call void @llvm.sentry.gpio.link("
                    f"i32 {gpio}, i8 {attr})"
                )
            elif isinstance(statement, (Assign, Trigger)):
                value = 1 if statement.value == "HIGH" else 0
                lines.append(
                    f"{prefix}call void @llvm.sentry.gpio.write(i32 %reg.{statement.target}, "
                    f"i1 {value})"
                )
            elif isinstance(statement, Log):
                string_id = intern(statement.message)
                size = max(1, len(statement.message.encode() + b"\\00"))
                lines.append(
                    f"{prefix}call void @llvm.sentry.log(i8* getelementptr "
                    f"inbounds ([{size} x i8], [{size} x i8]* @str.{string_id}, "
                    f"i64 0, i64 0))"
                )
            elif isinstance(statement, Delay):
                lines.append(f"{prefix}call void @llvm.sentry.timer.yield(i32 {statement.ms})")
            elif isinstance(statement, AtomicBlock):
                lines.append(f"{prefix}; atomic block")
                walk(statement.body, indent)
            elif isinstance(statement, IfBlock):
                label_then = block_label()
                label_end = block_label()
                expected = 1 if statement.state == "HIGH" else 0
                lines.append(
                    f"{prefix}%cond{block} = call i1 @llvm.sentry.gpio.read(i32 %reg.{statement.condition})"
                )
                lines.append(f"{prefix}br i1 %cond{block}, label %{label_then}, label %{label_end}")
                lines.append(f"{prefix}{label_then}:")
                walk(statement.body, indent)
                lines.append(f"{prefix}br label %{label_end}")
                lines.append(f"{prefix}{label_end}:")
            elif isinstance(statement, RepeatBlock):
                label_head = block_label()
                label_end = block_label()
                lines.append(f"{prefix}call void @llvm.sentry.repeat.begin(i32 {statement.count})")
                lines.append(f"{prefix}{label_head}:")
                lines.append(f"{prefix}; loop body (repeated {statement.count} times)")
                walk(statement.body, indent)
                lines.append(f"{prefix}br label %{label_head}")
                lines.append(f"{prefix}{label_end}:")
            elif isinstance(statement, WhileBlock):
                label_head = block_label()
                label_body = block_label()
                label_end = block_label()
                expected = 1 if statement.state == "HIGH" else 0
                lines.append(f"{prefix}{label_head}:")
                lines.append(
                    f"{prefix}%cond{block} = call i1 @llvm.sentry.gpio.read(i32 %reg.{statement.condition})"
                )
                lines.append(f"{prefix}br i1 %cond{block}, label %{label_body}, label %{label_end}")
                lines.append(f"{prefix}{label_body}:")
                walk(statement.body, indent)
                lines.append(f"{prefix}br label %{label_head}")
                lines.append(f"{prefix}{label_end}:")
            elif isinstance(statement, EveryBlock):
                label_head = block_label()
                label_end = block_label()
                lines.append(f"{prefix}{label_head}:")
                lines.append(f"{prefix}; timer task, yields every {statement.ms} ms")
                walk(statement.body, indent)
                lines.append(f"{prefix}call void @llvm.sentry.timer.yield(i32 {statement.ms})")
                lines.append(f"{prefix}br label %{label_head}")
                lines.append(f"{prefix}{label_end}:")
            elif isinstance(statement, AnalogRead):
                lines.append(
                    f"{prefix}%adc = call i32 @llvm.sentry.analog.read(i32 %reg.{statement.target})"
                )
            elif isinstance(statement, Authenticate):
                continue
            elif isinstance(statement, ForceOverride):
                lines.append(
                    f"{prefix}; rejected at compile time: FORCE OVERRIDE is never lowered"
                )

    walk(program.statements, 1)
    lines.append("}")
    for string_id, message in enumerate(strings):
        escaped = message.encode("unicode_escape").decode("ascii").replace('"', '\\"')
        size = max(1, len(message.encode() + b"\\00"))
        lines.append(f'@str.{string_id} = private unnamed_addr constant [{size} x i8] c"{escaped}\\00"')
    lines.append("")
    lines.append("attributes #0 = { nounwind }")
    return "\n".join(lines) + "\n"


def emit_map(tac):
    """Textual ESP32 deployment plan derived from optimized TAC records."""
    reg_to_pin = {}
    lines = [
        "; SentryPi ESP32 deployment plan (Arduino core)",
        "; format: <step> <action> [, <operand> ...]",
        "",
    ]

    def gpio_pin(reg):
        pin = reg_to_pin.get(reg, 0)
        if reg not in reg_to_pin:
            return None
        return _gpio(pin)

    for instruction in tac:
        op = instruction["op"]
        if op == "ALLOC_PIN":
            reg_to_pin[instruction["reg"]] = instruction["pin"]
            lines.append(
                f"link pin={instruction['pin']} gpio={_gpio(instruction['pin'])} "
                f"mode={instruction['mode']}"
            )
        elif op == "MAP_ALIAS":
            lines.append(f"alias reg={instruction['reg']} as {instruction['alias']}")
        elif op == "WRITE_BIT":
            gpio = gpio_pin(instruction["reg"])
            extra = "" if gpio is not None else " (unmapped)"
            level = "HIGH" if instruction["value"] else "LOW"
            lines.append(f"write gpio={gpio}{extra} {level}")
        elif op == "LOG":
            lines.append(f'log "{instruction["message"]}"')
        elif op == "DELAY":
            lines.append(f"delay ms={instruction['ms']}")
        elif op == "BRANCH":
            lines.append(f"if-read gpio={gpio_pin(instruction['reg'])} == {'HIGH' if instruction['value'] else 'LOW'}")
        elif op == "LOOP":
            lines.append(f"repeat count={instruction['count']}")
        elif op == "WHILE":
            lines.append(f"while-read gpio={gpio_pin(instruction['reg'])} == {'HIGH' if instruction['value'] else 'LOW'}")
        elif op == "TIMER":
            lines.append(f"every ms={instruction['ms']}")
        elif op == "JUMP":
            lines.append(f"loopback label={instruction['label']}")
        elif op == "ANALOG_READ":
            gpio = gpio_pin(instruction["reg"])
            lines.append(f"analog_read gpio={gpio}")
        elif op == "OVERRIDE":
            lines.append(f"forced_override rejected ({instruction['count']})")
    return "\n".join(lines) + "\n"
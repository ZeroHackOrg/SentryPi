import struct

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

MAGIC = b"SPI1"
OP_LINK = 1
OP_TRIGGER = 2
OP_LOG = 3
OP_BRANCH = 4
OP_OVERRIDE = 5
OP_DELAY = 6
OP_LOOP = 7
OP_WHILE = 8
OP_TIMER = 9
OP_JUMP = 10
OP_ANALOG = 11

MODE_ATTR = {"OUTPUT": 0, "INPUT": 1, "ANALOG": 2}
VALUE_ATTR = {"LOW": 0, "HIGH": 1}

PHYSICAL_TO_BCM = {
    3: 2, 5: 3, 7: 4, 8: 14, 10: 15, 11: 17, 12: 18, 13: 27,
    15: 22, 16: 23, 18: 24, 19: 10, 21: 9, 22: 25, 23: 11, 24: 8,
    26: 7, 27: 0, 28: 1, 29: 5, 31: 6, 32: 12, 33: 13, 35: 19,
    36: 16, 37: 26, 38: 20, 40: 21,
}

_OP_NAMES = {
    OP_LINK: "LINK",
    OP_TRIGGER: "TRIGGER",
    OP_LOG: "LOG",
    OP_BRANCH: "BRANCH",
    OP_OVERRIDE: "OVERRIDE",
    OP_DELAY: "DELAY",
    OP_LOOP: "LOOP",
    OP_WHILE: "WHILE",
    OP_TIMER: "TIMER",
    OP_JUMP: "JUMP",
    OP_ANALOG: "ANALOG",
}


def _records(tac):
    reg_to_pin = {}
    for instruction in tac:
        if instruction["op"] == "ALLOC_PIN":
            reg_to_pin[instruction["reg"]] = instruction["pin"]

    logs = []

    def add_log(message):
        if message not in logs:
            logs.append(message)
        return logs.index(message)

    records = []
    labels = {}
    pending = []
    begin_idx = {}
    jump_idx = {}

    def emit_record(record):
        records.append(record)
        return len(records) - 1

    for instruction in tac:
        op = instruction["op"]
        if op in ("LABEL", "MAP_ALIAS"):
            if op == "LABEL":
                labels[instruction["name"]] = len(records)
            continue
        if op == "ALLOC_PIN":
            mode = MODE_ATTR.get(instruction["mode"], 0)
            emit_record((OP_LINK, instruction["pin"], mode, 0))
            reg_to_pin[instruction["reg"]] = instruction["pin"]
        elif op == "WRITE_BIT":
            pin = reg_to_pin.get(instruction["reg"], 0)
            emit_record((OP_TRIGGER, pin, instruction["value"], 0))
        elif op == "LOG":
            emit_record((OP_LOG, 0, 0, add_log(instruction["message"])))
        elif op == "BRANCH":
            pin = reg_to_pin.get(instruction["reg"], 0)
            index = emit_record((OP_BRANCH, pin, instruction["value"], 0))
            pending.append((index, instruction["label"]))
        elif op == "OVERRIDE":
            emit_record((OP_OVERRIDE, 0, min(instruction["count"], 65535), 0))
        elif op == "DELAY":
            emit_record((OP_DELAY, 0, min(instruction["ms"], 65535), 0))
        elif op == "LOOP":
            index = emit_record((OP_LOOP, 0, min(instruction["count"], 65535), 0))
            begin_idx[instruction["label"]] = index
        elif op == "WHILE":
            pin = reg_to_pin.get(instruction["reg"], 0)
            index = emit_record((OP_WHILE, pin, instruction["value"], 0))
            begin_idx[instruction["label"]] = index
        elif op == "TIMER":
            index = emit_record((OP_TIMER, 0, min(instruction["ms"], 65535), 0))
            begin_idx[instruction["label"]] = index
        elif op == "JUMP":
            index = emit_record((OP_JUMP, 0, 0, 0))
            jump_idx[instruction["label"]] = index
        elif op == "ANALOG_READ":
            pin = reg_to_pin.get(instruction["reg"], 0)
            emit_record((OP_ANALOG, pin, 0, 0))

    for index, label in pending:
        records[index] = (records[index][0], records[index][1], records[index][2], labels.get(label, 0))
    for label, index in begin_idx.items():
        exit_target = jump_idx.get(label, index) + 1
        records[index] = (records[index][0], records[index][1], records[index][2], exit_target)
    for label, index in jump_idx.items():
        back_target = begin_idx.get(label, 0)
        records[index] = (records[index][0], records[index][1], records[index][2], back_target)

    return records, logs


def emit(tac):
    records, logs = _records(tac)
    out = bytearray(MAGIC)
    out += struct.pack("<I", len(records))
    for record in records:
        out += struct.pack("<BBHI", record[0], record[1], record[2], record[3])
    out += struct.pack("<I", len(logs))
    for message in logs:
        data = message.encode("utf-8")
        out += struct.pack("<I", len(data))
        out += data
    return bytes(out)


def emit_map(tac):
    records, logs = _records(tac)
    lines = [
        "; SentryPi hardened execution mapping",
        "; format: [idx] <op> pin=<n> value=<v> index=<i>",
        "",
    ]
    for idx, record in enumerate(records):
        opcode, pin, value, index = record
        name = _OP_NAMES[opcode]
        if opcode == OP_LINK:
            if value == 2:
                lines.append(f"[{idx}] {name:<8} pin={pin:<2} value=ANALOG")
            else:
                mode = "OUTPUT" if value == 0 else "INPUT"
                lines.append(f"[{idx}] {name:<8} pin={pin:<2} value={mode}")
        elif opcode == OP_TRIGGER:
            level = "HIGH" if value else "LOW"
            lines.append(f"[{idx}] {name:<8} pin={pin:<2} value={level}")
        elif opcode == OP_LOG:
            lines.append(f'[{idx}] {name:<8} pin=0  value=0    index={index} "{logs[index]}"')
        elif opcode == OP_BRANCH:
            level = "HIGH" if value else "LOW"
            lines.append(f"[{idx}] {name:<8} pin={pin:<2} value={level} -> record {index}")
        elif opcode == OP_OVERRIDE:
            lines.append(f"[{idx}] {name:<8} pin=0  count={value}")
        elif opcode == OP_DELAY:
            lines.append(f"[{idx}] {name:<8} pin=0  value={value}ms")
        elif opcode == OP_LOOP:
            lines.append(f"[{idx}] {name:<8} pin=0  count={value} -> exit record {index}")
        elif opcode == OP_WHILE:
            level = "HIGH" if value else "LOW"
            lines.append(f"[{idx}] {name:<8} pin={pin:<2} while={level} -> exit record {index}")
        elif opcode == OP_TIMER:
            lines.append(f"[{idx}] {name:<8} pin=0  every={value}ms -> exit record {index}")
        elif opcode == OP_JUMP:
            lines.append(f"[{idx}] {name:<8} pin=0  index={index} (loop back)")
        elif opcode == OP_ANALOG:
            lines.append(f"[{idx}] {name:<8} pin={pin:<2} analog_read")
    return "\n".join(lines) + "\n"


def _bcm(pin):
    return PHYSICAL_TO_BCM.get(pin, pin)


def synthesize_bash(program):
    links = {}
    for statement in program.statements:
        if isinstance(statement, LinkPin):
            links[statement.target] = (statement.pin, statement.mode)

    lines = [
        "#!/bin/bash",
        f"# Compiled securely via SentryPi Framework v{VERSION}",
        "# Targets Linux sysfs node: /sys/class/gpio (BCM GPIO numbering)",
        "",
    ]

    def allocate(pin, mode):
        gpio = _bcm(pin)
        if mode == "ANALOG":
            lines.append(f"# ANALOG channel {pin} mapped to GPIO {gpio}; requires an ADC backend")
            return
        lines.append(f"if [ ! -d /sys/class/gpio/gpio{gpio} ]; then echo {gpio} > /sys/class/gpio/export; fi")
        direction = "in" if mode == "INPUT" else "out"
        lines.append(f"echo {direction} > /sys/class/gpio/gpio{gpio}/direction")

    def walk(statements, indent):
        prefix = "  " * indent
        for statement in statements:
            if isinstance(statement, LinkPin):
                allocate(statement.pin, statement.mode or "INPUT")
            elif isinstance(statement, (Assign, Trigger)):
                pin, mode = links.get(statement.target, (0, "OUTPUT"))
                if mode == "ANALOG":
                    lines.append(f"{prefix}# rejected at compile time: write to analog channel")
                    continue
                value = 1 if statement.value == "HIGH" else 0
                lines.append(f"{prefix}echo {value} > /sys/class/gpio/gpio{_bcm(pin)}/value")
            elif isinstance(statement, Log):
                lines.append(f'{prefix}echo "{statement.message}"')
            elif isinstance(statement, Delay):
                lines.append(f"{prefix}sleep {statement.ms / 1000:.3f}")
            elif isinstance(statement, AtomicBlock):
                lines.append(f"{prefix}# atomic hardware block")
                walk(statement.body, indent)
            elif isinstance(statement, IfBlock):
                pin, _ = links.get(statement.condition, (0, "INPUT"))
                expected = 1 if statement.state == "HIGH" else 0
                lines.append(
                    f'{prefix}if [ "$(cat /sys/class/gpio/gpio{_bcm(pin)}/value)" = '
                    f'"{expected}" ]; then'
                )
                walk(statement.body, indent + 1)
                lines.append(f"{prefix}fi")
            elif isinstance(statement, RepeatBlock):
                lines.append(f"{prefix}for __iter in $(seq 1 {statement.count}); do")
                walk(statement.body, indent + 1)
                lines.append(f"{prefix}done")
            elif isinstance(statement, WhileBlock):
                pin, _ = links.get(statement.condition, (0, "INPUT"))
                expected = 1 if statement.state == "HIGH" else 0
                lines.append(
                    f'{prefix}while [ "$(cat /sys/class/gpio/gpio{_bcm(pin)}/value)" = '
                    f'"{expected}" ]; do'
                )
                walk(statement.body, indent + 1)
                lines.append(f"{prefix}done")
            elif isinstance(statement, EveryBlock):
                lines.append(f"{prefix}# cooperative timer task, yields every {statement.ms} ms")
                lines.append(f"{prefix}while :; do")
                walk(statement.body, indent + 1)
                lines.append(f"{prefix}sleep {statement.ms / 1000:.3f}")
                lines.append(f"{prefix}done")
            elif isinstance(statement, AnalogRead):
                lines.append(
                    f"{prefix}# ANALOG_READ {statement.target}: value sampled by the ADC backend"
                )
            elif isinstance(statement, ForceOverride):
                lines.append(
                    f"{prefix}# rejected at compile time: FORCE OVERRIDE is never synthesized"
                )

    walk(program.statements, 0)
    return "\n".join(lines) + "\n"


_DRIVER_PREAMBLE = '''\
import os
import mmap
import struct
import time

GPIO_BASE = "/dev/gpiomem"

try:
    _fd = os.open(GPIO_BASE, os.O_RDWR | os.O_SYNC)
    _mem = mmap.mmap(_fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
except OSError:
    print("Hardware Access Denied: run payload with sudo / GPIO group membership.")
    raise SystemExit(1)


def set_pin_mode(pin, mode):
    register = (pin // 10) * 4
    shift = (pin % 10) * 3
    _mem.seek(register)
    current = struct.unpack("I", _mem.read(4))[0]
    current &= ~(7 << shift)
    current |= (1 if mode == "out" else 0) << shift
    _mem.seek(register)
    _mem.write(struct.pack("I", current))


def write_pin(pin, value):
    offset = 0x1C if value else 0x28
    _mem.seek(offset)
    _mem.write(struct.pack("I", 1 << pin))


def read_pin(pin):
    _mem.seek(0x34)
    level = struct.unpack("I", _mem.read(4))[0]
    return 1 if (level >> pin) & 1 else 0


def read_analog(channel_pin):
    import glob

    candidates = sorted(
        glob.glob(f"/sys/bus/iio/devices/iio:device*/in_voltage{channel_pin}_raw")
    )
    if not candidates:
        raise RuntimeError(
            f"ADC channel {channel_pin} not found; map it to an enabled IIO node"
        )
    with open(candidates[0]) as handle:
        return int(handle.read().strip())
'''


def synthesize_driver(program):
    links = {}
    for statement in program.statements:
        if isinstance(statement, LinkPin):
            links[statement.target] = (statement.pin, statement.mode)

    lines = [
        f"# Compiled via SentryPi High-Speed Backend Engine v{VERSION}",
        "# Maps Raspberry Pi peripheral registers via /dev/gpiomem (BCM numbering).",
        _DRIVER_PREAMBLE,
    ]

    def walk(statements, indent):
        prefix = "    " * indent
        for statement in statements:
            if isinstance(statement, LinkPin):
                if statement.mode == "ANALOG":
                    lines.append(
                        f"{prefix}# analog channel {statement.pin}: sampled via read_analog()"
                    )
                    continue
                gpio = _bcm(statement.pin)
                mode = "out" if statement.mode in ("OUTPUT",) else "in"
                lines.append(f"{prefix}set_pin_mode({gpio}, {mode!r})")
            elif isinstance(statement, (Assign, Trigger)):
                pin, mode = links.get(statement.target, (0, "OUTPUT"))
                if mode == "ANALOG":
                    lines.append(f"{prefix}# rejected at compile time: write to analog channel")
                    continue
                value = 1 if statement.value == "HIGH" else 0
                lines.append(f"{prefix}write_pin({_bcm(pin)}, {value})")
            elif isinstance(statement, Log):
                lines.append(f"{prefix}print({statement.message!r})")
            elif isinstance(statement, Delay):
                lines.append(f"{prefix}time.sleep({statement.ms / 1000:.3f})")
            elif isinstance(statement, AtomicBlock):
                lines.append(f"{prefix}# atomic hardware block")
                walk(statement.body, indent)
            elif isinstance(statement, IfBlock):
                pin, _ = links.get(statement.condition, (0, "INPUT"))
                expected = 1 if statement.state == "HIGH" else 0
                lines.append(f"{prefix}if read_pin({_bcm(pin)}) == {expected}:")
                walk(statement.body, indent + 1)
            elif isinstance(statement, RepeatBlock):
                lines.append(f"{prefix}for __iter in range({statement.count}):")
                walk(statement.body, indent + 1)
            elif isinstance(statement, WhileBlock):
                pin, _ = links.get(statement.condition, (0, "INPUT"))
                expected = 1 if statement.state == "HIGH" else 0
                lines.append(
                    f"{prefix}while read_pin({_bcm(pin)}) == {expected}:"
                )
                walk(statement.body, indent + 1)
            elif isinstance(statement, EveryBlock):
                lines.append(f"{prefix}# cooperative timer task, yields every {statement.ms} ms")
                lines.append(f"{prefix}while True:")
                walk(statement.body, indent + 1)
                lines.append(f"{prefix}    time.sleep({statement.ms / 1000:.3f})")
            elif isinstance(statement, AnalogRead):
                pin, _ = links.get(statement.target, (0, 0))
                lines.append(f"{prefix}read_analog({pin})")
            elif isinstance(statement, Authenticate):
                continue
            elif isinstance(statement, ForceOverride):
                lines.append(f"{prefix}# rejected at compile time: FORCE OVERRIDE is never synthesized")

    walk(program.statements, 0)
    return "\n".join(lines) + "\n"
import struct

from ._version import VERSION
from .ast_nodes import Assign, AtomicBlock, Authenticate, Delay, ForceOverride, IfBlock, LinkPin, Log, Trigger

MAGIC = b"SPI1"
OP_LINK = 1
OP_TRIGGER = 2
OP_LOG = 3
OP_BRANCH = 4
OP_OVERRIDE = 5
OP_DELAY = 6

MODE_ATTR = {"OUTPUT": 0, "INPUT": 1}
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
            mode = 0 if instruction["mode"] == "OUTPUT" else 1
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

    for index, label in pending:
        records[index] = (records[index][0], records[index][1], records[index][2], labels.get(label, 0))

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
        lines.append(f"if [ ! -d /sys/class/gpio/gpio{gpio} ]; then echo {gpio} > /sys/class/gpio/export; fi")
        direction = "in" if mode == "INPUT" else "out"
        lines.append(f"echo {direction} > /sys/class/gpio/gpio{gpio}/direction")

    def walk(statements, indent):
        prefix = "  " * indent
        for statement in statements:
            if isinstance(statement, LinkPin):
                allocate(statement.pin, statement.mode or "INPUT")
            elif isinstance(statement, (Assign, Trigger)):
                pin, _ = links.get(statement.target, (0, "OUTPUT"))
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
                gpio = _bcm(statement.pin)
                mode = "out" if statement.mode in ("OUTPUT",) else "in"
                lines.append(f"{prefix}set_pin_mode({gpio}, {mode!r})")
            elif isinstance(statement, (Assign, Trigger)):
                pin, _ = links.get(statement.target, (0, "OUTPUT"))
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
            elif isinstance(statement, Authenticate):
                continue
            elif isinstance(statement, ForceOverride):
                lines.append(f"{prefix}# rejected at compile time: FORCE OVERRIDE is never synthesized")

    walk(program.statements, 0)
    return "\n".join(lines) + "\n"
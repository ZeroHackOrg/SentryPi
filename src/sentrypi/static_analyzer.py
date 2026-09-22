from .ast_nodes import Assign, AtomicBlock, Authenticate, Delay, ForceOverride, IfBlock, LinkPin, Trigger

MAX_REGISTER_ALLOCATION = 256
MAX_STRING_BYTES = MAX_REGISTER_ALLOCATION
VALID_PIN_MIN = 1
VALID_PIN_MAX = 40
MAX_TOGGLES_WITHOUT_DELAY = 20
SYSTEM_COMPONENTS = {"SYSTEM_CLOCK", "SYSTEM_BUS"}
PROTECTED_RESOURCES = {"SYSTEM_CLOCK", "SYSTEM_BUS", "KERNEL_REGISTERS"}

RULE_INVALID_PIN = "invalid_pin"
RULE_RESERVED_PIN = "reserved_pin"
RULE_SYSTEM_COMPONENT = "system_component"
RULE_INPUT_WRITE = "input_write"
RULE_OVERFLOW = "overflow"
RULE_PROTECTED = "protected_resource"
RULE_TOCTOU = "toctou"
RULE_OVERLOAD = "overload"


class SecurityIssue:
    def __init__(self, severity, line, message, rule=None):
        self.severity = severity
        self.line = line
        self.message = message
        self.rule = rule

    def __repr__(self):
        return f"SecurityIssue({self.severity}, {self.line}, {self.message!r})"


class SentrySecurityFirewall:
    RESERVED_SYSTEM_PINS = [1, 2, 4, 6, 9, 14, 20, 25, 30, 34, 39]

    def __init__(self):
        self.issues = []
        self.linked = {}
        self.toggle_counts = {}
        self.overload_flagged = set()

    def analyze(self, program):
        self._index(program.statements)
        self._walk(program.statements, atomic_depth=0)
        return self.issues

    def _index(self, statements):
        for statement in statements:
            if isinstance(statement, LinkPin):
                self.linked[statement.target] = (statement.pin, statement.mode)
            elif isinstance(statement, AtomicBlock):
                self._index(statement.body)
            elif isinstance(statement, IfBlock):
                self._index(statement.body)

    def _walk(self, statements, atomic_depth):
        for statement in statements:
            if isinstance(statement, LinkPin):
                self._audit_link(statement)
            elif isinstance(statement, (Assign, Trigger)):
                self._audit_write(statement)
                self._track_toggle(statement)
            elif isinstance(statement, Delay):
                self.toggle_counts.clear()
            elif isinstance(statement, AtomicBlock):
                self._walk(statement.body, atomic_depth + 1)
            elif isinstance(statement, IfBlock):
                self._audit_if(statement, atomic_depth)
                self._walk(statement.body, atomic_depth)
            elif isinstance(statement, ForceOverride):
                self._audit_override(statement)
            elif isinstance(statement, Authenticate):
                continue

    def _audit_link(self, statement):
        pin = statement.pin
        if pin < VALID_PIN_MIN or pin > VALID_PIN_MAX:
            self.issues.append(
                SecurityIssue(
                    "ERROR",
                    statement.line,
                    f"Security Exception! Invalid Pin {pin}: physical GPIO header range is "
                    f"{VALID_PIN_MIN}-{VALID_PIN_MAX}.",
                    RULE_INVALID_PIN,
                )
            )
            return
        if pin in self.RESERVED_SYSTEM_PINS:
            self.issues.append(
                SecurityIssue(
                    "ERROR",
                    statement.line,
                    f"Security Exception! System Threat Detected! Attempted hijack of Reserved Pin {pin:02d}.",
                    RULE_RESERVED_PIN,
                )
            )
            return
        if statement.target in SYSTEM_COMPONENTS:
            self.issues.append(
                SecurityIssue(
                    "ERROR",
                    statement.line,
                    f"Security Exception! Unauthorized access to system component {statement.target}.",
                    RULE_SYSTEM_COMPONENT,
                )
            )

    def _audit_write(self, statement):
        target = statement.target
        if target not in self.linked:
            return
        pin, mode = self.linked[target]
        if mode == "INPUT":
            self.issues.append(
                SecurityIssue(
                    "ERROR",
                    statement.line,
                    f"Security Exception! Attempted to write a payload to INPUT peripheral '{target}'.",
                    RULE_INPUT_WRITE,
                )
            )
        if pin in self.RESERVED_SYSTEM_PINS:
            self.issues.append(
                SecurityIssue(
                    "ERROR",
                    statement.line,
                    f"Security Exception! System Threat Detected! Attempted write to Reserved Pin {pin:02d}.",
                    RULE_RESERVED_PIN,
                )
            )

    def _audit_if(self, statement, atomic_depth):
        if statement.condition in self.linked and atomic_depth == 0:
            self.issues.append(
                SecurityIssue(
                    "WARN",
                    statement.line,
                    f"Potential TOCTOU race: IF queries peripheral '{statement.condition}' "
                    f"outside an atomic hardware block. Wrap it in ATOMIC ... END.",
                    RULE_TOCTOU,
                )
            )

    def _track_toggle(self, statement):
        target = statement.target
        if target not in self.linked:
            return
        pin, mode = self.linked[target]
        if mode == "INPUT":
            return
        count = self.toggle_counts.get(pin, 0) + 1
        self.toggle_counts[pin] = count
        if count > MAX_TOGGLES_WITHOUT_DELAY and pin not in self.overload_flagged:
            self.overload_flagged.add(pin)
            self.issues.append(
                SecurityIssue(
                    "WARN",
                    statement.line,
                    f"Current overload limit: pin {pin} toggled {count} times without a DELAY "
                    f"safety barrier; risk of overcurrent. Insert DELAY <ms> MS.",
                    RULE_OVERLOAD,
                )
            )

    def _audit_override(self, statement):
        effective = len(statement.value) * statement.count
        if effective > MAX_STRING_BYTES:
            self.issues.append(
                SecurityIssue(
                    "ERROR",
                    statement.line,
                    f"Buffer overflow vulnerability detected! String size ({effective} bytes) exceeds "
                    f"safe buffer allotment of {MAX_STRING_BYTES} bytes.",
                    RULE_OVERFLOW,
                )
            )
        if statement.target in PROTECTED_RESOURCES:
            self.issues.append(
                SecurityIssue(
                    "ERROR",
                    statement.line,
                    f"Security Exception! Unauthorized write to protected system resource "
                    f"'{statement.target}'.",
                    RULE_PROTECTED,
                )
            )


HARD_ESCALATION_RULES = {RULE_TOCTOU, RULE_OVERLOAD}


def analyze(program, hard=False):
    issues = SentrySecurityFirewall().analyze(program)
    if hard:
        for issue in issues:
            if issue.severity == "WARN" and issue.rule in HARD_ESCALATION_RULES:
                issue.severity = "ERROR"
    return issues
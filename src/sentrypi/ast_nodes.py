from dataclasses import dataclass, field


@dataclass
class Program:
    statements: list = field(default_factory=list)


@dataclass
class Authenticate:
    signature: str
    line: int


@dataclass
class LinkPin:
    pin: int
    target: str
    mode: str
    line: int


@dataclass
class Assign:
    target: str
    value: str
    line: int


@dataclass
class Trigger:
    target: str
    value: str
    line: int


@dataclass
class Log:
    message: str
    line: int


@dataclass
class Delay:
    ms: int
    line: int


@dataclass
class AtomicBlock:
    body: list
    line: int


@dataclass
class IfBlock:
    condition: str
    body: list
    line: int
    state: str = "HIGH"


@dataclass
class ForceOverride:
    target: str
    value: str
    count: int
    line: int
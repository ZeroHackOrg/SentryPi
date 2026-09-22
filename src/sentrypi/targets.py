"""Backend target registry.

SentryPi's codegen is target-selected through a small registry so third-party
and enterprise backends (ESP32, STM32, Arduino, AI edge accelerators) can be
plugged into the pipeline without modifying the compiler core.

The default target is ``arm`` (Raspberry Pi). Select another target with the
``SENTRYPI_TARGET`` environment variable; enterprise packs may register
proprietary targets via ``targets.register(...)`` before invoking the
compiler.
"""

import os
from dataclasses import dataclass, field

from . import target_arm

DEFAULT_TARGET = "arm"
TARGET_ENV = "SENTRYPI_TARGET"


@dataclass(frozen=True)
class Target:
    """Contract every backend must satisfy.

    ``emit`` / ``emit_map`` operate on optimized TAC; ``synthesize_bash`` and
    ``synthesize_driver`` operate on the verified AST. Backends that cannot
    produce a given artifact declare so via the capability flags.
    """

    id: str
    name: str
    boards: tuple = ()
    emit: callable = None
    emit_map: callable = None
    synthesize_bash: callable = None
    synthesize_driver: callable = None
    emits_bin: bool = True
    emits_map: bool = True
    emits_sh: bool = True
    emits_driver: bool = True
    metadata: dict = field(default_factory=dict)


TARGETS = {}


def register(target):
    """Register a backend ``Target`` for later selection."""
    if not isinstance(target, Target):
        raise TypeError("register() expects a Target instance")
    if not target.id:
        raise ValueError("target.id must be a non-empty string")
    TARGETS[target.id] = target
    return target


def get(target_id=None):
    """Resolve a target by id (default: env ``SENTRYPI_TARGET`` or ``arm``)."""
    identifier = target_id or os.environ.get(TARGET_ENV) or DEFAULT_TARGET
    try:
        return TARGETS[identifier]
    except KeyError:
        raise KeyError(
            f"Unknown architecture target '{identifier}'. "
            f"Registered targets: {', '.join(sorted(TARGETS))}. "
            f"Set {TARGET_ENV} to select a backend, or ship a Target plugin."
        )


def list_targets():
    return tuple(TARGETS)


ARM = register(
    Target(
        id="arm",
        name="Raspberry Pi ARM (BCM2835 / BCM2711 / RP1)",
        boards=("Raspberry Pi 4B", "Raspberry Pi 5"),
        emit=target_arm.emit,
        emit_map=target_arm.emit_map,
        synthesize_bash=target_arm.synthesize_bash,
        synthesize_driver=target_arm.synthesize_driver,
        metadata={"physical_to_bcm": target_arm.PHYSICAL_TO_BCM},
    )
)
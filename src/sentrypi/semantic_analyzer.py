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
from .static_analyzer import SecurityIssue


class SemanticAnalyzer:
    def analyze(self, program):
        issues = []
        linked = {}
        pinned = {}
        statement_index = 0

        def register(statement):
            target = statement.target
            if target in linked:
                issues.append(
                    SecurityIssue(
                        "WARN",
                        statement.line,
                        f"Component '{target}' is already linked to pin {linked[target][0]}.",
                    )
                )
            if statement.pin in pinned:
                issues.append(
                    SecurityIssue(
                        "WARN",
                        statement.line,
                        f"Pin {statement.pin} is linked more than once "
                        f"(component '{pinned[statement.pin]}').",
                    )
                )
            linked[statement.target] = (statement.pin, statement.mode)
            pinned[statement.pin] = statement.target

        def check_reference(name, line):
            if name not in linked:
                issues.append(
                    SecurityIssue(
                        "WARN",
                        line,
                        f"Unknown component '{name}'; no LINK directive found.",
                    )
                )

        def walk(statements, position):
            for statement in statements:
                if isinstance(statement, LinkPin):
                    register(statement)
                elif isinstance(statement, (Assign, Trigger)):
                    check_reference(statement.target, statement.line)
                elif isinstance(statement, IfBlock):
                    check_reference(statement.condition, statement.line)
                    walk(statement.body, position)
                elif isinstance(statement, AtomicBlock):
                    walk(statement.body, position)
                elif isinstance(statement, RepeatBlock):
                    walk(statement.body, position)
                elif isinstance(statement, WhileBlock):
                    check_reference(statement.condition, statement.line)
                    walk(statement.body, position)
                elif isinstance(statement, EveryBlock):
                    walk(statement.body, position)
                elif isinstance(statement, AnalogRead):
                    check_reference(statement.target, statement.line)
                elif isinstance(statement, Authenticate):
                    if position != 0:
                        issues.append(
                            SecurityIssue(
                                "WARN",
                                statement.line,
                                "AUTHENTICATE must be the first statement of the program.",
                            )
                        )
                elif isinstance(statement, ForceOverride):
                    if statement.target != "BUFFER":
                        check_reference(statement.target, statement.line)
                elif isinstance(statement, Log):
                    continue
                elif isinstance(statement, Delay):
                    continue
                position += 1

        walk(program.statements, statement_index)
        return issues
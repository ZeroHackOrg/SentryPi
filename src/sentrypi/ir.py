from .ast_nodes import Assign, AtomicBlock, Authenticate, Delay, ForceOverride, IfBlock, LinkPin, Log, Trigger


class IRGenerator:
    def generate(self, program):
        self.tac = []
        self.registers = {}
        self.counter = 0
        self.label_count = 0
        self._walk(program.statements)
        return self.tac

    def _temp(self):
        name = f"t{self.counter}"
        self.counter += 1
        return name

    def _label(self):
        name = f"L{self.label_count}"
        self.label_count += 1
        return name

    def _reference(self, target):
        return self.registers.get(target, self._temp())

    def _walk(self, statements):
        for statement in statements:
            if isinstance(statement, LinkPin):
                register = self._temp()
                self.tac.append(
                    {
                        "op": "ALLOC_PIN",
                        "pin": statement.pin,
                        "mode": statement.mode or "INPUT",
                        "reg": register,
                    }
                )
                self.tac.append({"op": "MAP_ALIAS", "reg": register, "alias": statement.target})
                self.registers[statement.target] = register
            elif isinstance(statement, (Assign, Trigger)):
                register = self._reference(statement.target)
                value = 1 if statement.value == "HIGH" else 0
                self.tac.append({"op": "WRITE_BIT", "reg": register, "value": value})
            elif isinstance(statement, Log):
                self.tac.append({"op": "LOG", "message": statement.message})
            elif isinstance(statement, Delay):
                self.tac.append({"op": "DELAY", "ms": statement.ms})
            elif isinstance(statement, AtomicBlock):
                self._walk(statement.body)
            elif isinstance(statement, Authenticate):
                continue
            elif isinstance(statement, IfBlock):
                register = self._reference(statement.condition)
                label = self._label()
                value = 1 if statement.state == "HIGH" else 0
                self.tac.append({"op": "BRANCH", "reg": register, "value": value, "label": label})
                self.tac.append({"op": "LABEL", "name": label})
                self._walk(statement.body)
            elif isinstance(statement, ForceOverride):
                self.tac.append(
                    {"op": "OVERRIDE", "target": statement.target, "count": statement.count}
                )
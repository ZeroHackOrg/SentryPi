from .ast_nodes import (
    Assign,
    AtomicBlock,
    Authenticate,
    Delay,
    ForceOverride,
    IfBlock,
    LinkPin,
    Log,
    Program,
    Trigger,
)


class ParseError(Exception):
    def __init__(self, message, line):
        super().__init__(message)
        self.message = message
        self.line = line


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.errors = []

    def current(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self):
        token = self.current()
        self.pos += 1
        return token

    def _describe(self, token):
        return repr(token.value) if token else "end of file"

    def expect(self, kinds):
        allowed = kinds if isinstance(kinds, tuple) else (kinds,)
        token = self.current()
        if token is None or token.kind not in allowed:
            where = token.line if token else 0
            raise ParseError(
                f"Expected one of {', '.join(allowed)} but found {self._describe(token)}.",
                where,
            )
        return self.advance()

    def _synchronize(self):
        current = self.current()
        if current is None:
            return
        start_line = current.line
        while self.current() is not None:
            token = self.current()
            if token.kind == "END":
                self.advance()
                return
            if token.line != start_line:
                return
            self.advance()

    def parse_program(self):
        program = Program()
        while self.current() is not None:
            try:
                program.statements.append(self.parse_statement())
            except ParseError as error:
                self.errors.append(error)
                self._synchronize()
        return program

    def parse_statement(self):
        token = self.current()
        if token is None:
            raise ParseError("Unexpected end of file.", 0)
        if token.kind == "LINK":
            return self.parse_link()
        if token.kind == "TRIGGER":
            return self.parse_trigger()
        if token.kind == "IDENT":
            return self.parse_assign()
        if token.kind == "LOG":
            return self.parse_log()
        if token.kind == "IF":
            return self.parse_if()
        if token.kind == "ATOMIC":
            return self.parse_atomic()
        if token.kind == "DELAY":
            return self.parse_delay()
        if token.kind == "AUTHENTICATE":
            return self.parse_authenticate()
        if token.kind == "FORCE":
            return self.parse_force()
        raise ParseError(f"Unexpected {self._describe(token)} at statement start.", token.line)

    def parse_link(self):
        heading = self.current()
        self.expect("LINK")
        self.expect("PIN")
        pin = self.expect("INT").value
        self.expect("TO")
        target = self.expect("IDENT").value
        mode = None
        if self.current() is not None and self.current().kind == "AS":
            self.advance()
            mode = self.expect(("OUTPUT", "INPUT")).kind
        return LinkPin(pin, target, mode, heading.line)

    def parse_assign(self):
        heading = self.current()
        target = self.expect("IDENT").value
        value = self.expect(("HIGH", "LOW")).kind
        return Assign(target, value, heading.line)

    def parse_trigger(self):
        heading = self.current()
        self.expect("TRIGGER")
        target = self.expect("IDENT").value
        value = self.expect(("HIGH", "LOW")).kind
        return Trigger(target, value, heading.line)

    def parse_log(self):
        heading = self.current()
        self.expect("LOG")
        message = self.expect("STRING").value
        return Log(message, heading.line)

    def parse_delay(self):
        heading = self.current()
        self.expect("DELAY")
        ms = self.expect("INT").value
        self.expect("MS")
        return Delay(ms, heading.line)

    def parse_authenticate(self):
        heading = self.current()
        self.expect("AUTHENTICATE")
        self.expect("WITH")
        signature = self.expect("STRING").value
        return Authenticate(signature, heading.line)

    def parse_atomic(self):
        heading = self.current()
        self.expect("ATOMIC")
        body = []
        while True:
            token = self.current()
            if token is None:
                raise ParseError("Expected END to close ATOMIC block.", heading.line)
            if token.kind == "END":
                self.advance()
                break
            body.append(self.parse_statement())
        return AtomicBlock(body, heading.line)

    def parse_if(self):
        heading = self.current()
        self.expect("IF")
        condition = self.expect("IDENT").value
        if self.current() is not None and self.current().kind == "IS":
            self.advance()
        state = self.expect(("HIGH", "LOW")).kind
        self.expect("THEN")
        body = []
        while True:
            token = self.current()
            if token is None:
                raise ParseError("Expected END to close IF block.", heading.line)
            if token.kind == "END":
                self.advance()
                break
            body.append(self.parse_statement())
        return IfBlock(condition, body, heading.line, state)

    def parse_force(self):
        heading = self.current()
        self.expect("FORCE")
        self.expect("OVERRIDE")
        target = self.expect(("IDENT", "BUFFER")).value
        self.expect("WITH")
        value = self.expect("STRING").value
        count = 1
        if self.current() is not None and self.current().kind == "MUL":
            self.advance()
            count = self.expect("INT").value
        return ForceOverride(target, value, count, heading.line)
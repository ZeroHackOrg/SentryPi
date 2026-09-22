from collections import namedtuple

Token = namedtuple("Token", ["kind", "value", "line", "column"])

IDENTIFIER_MAX = 32
STRING_MAX_BYTES = 256

KEYWORDS = {
    "LINK",
    "PIN",
    "TO",
    "AS",
    "OUTPUT",
    "INPUT",
    "TRIGGER",
    "HIGH",
    "LOW",
    "LOG",
    "IF",
    "IS",
    "THEN",
    "END",
    "FORCE",
    "OVERRIDE",
    "BUFFER",
    "WITH",
    "MUL",
    "AUTHENTICATE",
    "ATOMIC",
    "DELAY",
    "MS",
}

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


class LexError(Exception):
    def __init__(self, message, line, column):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


def tokenize(source):
    tokens = []
    length = len(source)
    index = 0
    line = 1
    column = 1
    while index < length:
        char = source[index]
        if char == "\n":
            line += 1
            column = 1
            index += 1
            continue
        if char in " \t\r":
            index += 1
            column += 1
            continue
        if char == "#":
            while index < length and source[index] != "\n":
                index += 1
            continue
        if char == '"':
            start_line = line
            start_col = column
            index += 1
            column += 1
            chars = []
            while index < length and source[index] != '"':
                current = source[index]
                if current == "\\":
                    if index + 1 >= length:
                        raise LexError("Unterminated string literal.", start_line, start_col)
                    nxt = source[index + 1]
                    chars.append(_ESCAPES.get(nxt, nxt))
                    index += 2
                    column += 2
                    continue
                chars.append(current)
                index += 1
                column += 1
            if index >= length:
                raise LexError("Unterminated string literal.", start_line, start_col)
            index += 1
            column += 1
            value = "".join(chars)
            if len(value.encode("utf-8")) > STRING_MAX_BYTES:
                raise LexError(
                    f"Buffer overflow vulnerability detected! String size ({len(value.encode('utf-8'))} bytes) "
                    f"exceeds safe buffer allotment of {STRING_MAX_BYTES} bytes.",
                    start_line,
                    start_col,
                )
            tokens.append(Token("STRING", value, start_line, start_col))
            continue
        if char.isdigit():
            start = index
            start_col = column
            while index < length and source[index].isdigit():
                index += 1
                column += 1
            tokens.append(Token("INT", int(source[start:index]), line, start_col))
            continue
        if char == "*":
            tokens.append(Token("MUL", "*", line, column))
            index += 1
            column += 1
            continue
        if char.isalpha() or char == "_":
            start = index
            start_col = column
            while index < length and (source[index].isalnum() or source[index] == "_"):
                index += 1
                column += 1
            text = source[start:index]
            if len(text) > IDENTIFIER_MAX:
                raise LexError(
                    f"Buffer overflow vulnerability detected! Identifier exceeds the "
                    f"{IDENTIFIER_MAX}-character maximum bound.",
                    line,
                    start_col,
                )
            kinds = text if text in KEYWORDS else "IDENT"
            tokens.append(Token(kinds, text, line, start_col))
            continue
        raise LexError(f"Unexpected character {char!r}.", line, column)
    return tokens
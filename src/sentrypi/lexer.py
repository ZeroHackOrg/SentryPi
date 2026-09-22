import re
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
    "ANALOG",
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
    "REPEAT",
    "TIMES",
    "WHILE",
    "EVERY",
    "ANALOG_READ",
    "AUTHENTICATE",
    "ATOMIC",
    "DELAY",
    "MS",
}

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}

# Lexeme table: ordered (kind, regular expression) pairs. The first pattern
# that matches at the current position wins. Whitespace, newlines, and
# comments advance the scanner without producing tokens.
_LEXEMES = [
    ("STRING", r'"(?:\\.|[^"\\])*"'),
    ("INT", r"\d+"),
    ("MUL", r"\*"),
    ("IDENT", r"[A-Za-z_][A-Za-z0-9_]*"),
    ("WHITESPACE", r"[ \t\r]+"),
    ("NEWLINE", r"\n"),
    ("COMMENT", r"#[^\n]*"),
]

_COMPILED = [(kind, re.compile(pattern)) for kind, pattern in _LEXEMES]


class LexError(Exception):
    def __init__(self, message, line, column):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


def _escape_string(raw):
    chars = []
    index = 0
    while index < len(raw):
        current = raw[index]
        if current == "\\" and index + 1 < len(raw):
            chars.append(_ESCAPES.get(raw[index + 1], raw[index + 1]))
            index += 2
            continue
        chars.append(current)
        index += 1
    return "".join(chars)


def tokenize(source):
    tokens = []
    line = 1
    line_start = 0
    index = 0
    while index < len(source):
        matched = False
        for kind, pattern in _COMPILED:
            match = pattern.match(source, index)
            if match is None:
                continue
            matched = True
            value = match.group(0)
            column = index - line_start + 1
            if kind == "WHITESPACE":
                index = match.end()
                break
            if kind == "NEWLINE":
                index = match.end()
                line += 1
                line_start = index
                break
            if kind == "COMMENT":
                index = match.end()
                break
            if kind == "STRING":
                text = _escape_string(value[1:-1])
                if len(text.encode("utf-8")) > STRING_MAX_BYTES:
                    raise LexError(
                        f"Buffer overflow vulnerability detected! String size ({len(text.encode('utf-8'))} bytes) "
                        f"exceeds safe buffer allotment of {STRING_MAX_BYTES} bytes.",
                        line,
                        column,
                    )
                tokens.append(Token("STRING", text, line, column))
            elif kind == "INT":
                tokens.append(Token("INT", int(value), line, column))
            elif kind == "IDENT":
                if len(value) > IDENTIFIER_MAX:
                    raise LexError(
                        f"Buffer overflow vulnerability detected! Identifier exceeds the "
                        f"{IDENTIFIER_MAX}-character maximum bound.",
                        line,
                        column,
                    )
                kind = value if value in KEYWORDS else "IDENT"
                tokens.append(Token(kind, value, line, column))
            else:
                tokens.append(Token(kind, value, line, column))
            index = match.end()
            break
        if not matched:
            if source[index] == '"':
                raise LexError("Unterminated string literal.", line, index - line_start + 1)
            raise LexError(f"Unexpected character {source[index]!r}.", line, index - line_start + 1)
    return tokens
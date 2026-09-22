import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.lexer import IDENTIFIER_MAX, STRING_MAX_BYTES, LexError, tokenize


class TestLexer(unittest.TestCase):
    def test_keywords_and_identifiers(self):
        tokens = tokenize("LINK PIN 18 TO TARGET_LED AS OUTPUT\n")
        kinds = [token.kind for token in tokens]
        self.assertEqual(kinds, ["LINK", "PIN", "INT", "TO", "IDENT", "AS", "OUTPUT"])

    def test_integer_value(self):
        tokens = tokenize("LINK PIN 23 TO MOTION_SENSOR")
        self.assertEqual(tokens[2].value, 23)

    def test_string_literal(self):
        tokens = tokenize('LOG "Hello World"')
        self.assertEqual(tokens[0].kind, "LOG")
        self.assertEqual(tokens[1].kind, "STRING")
        self.assertEqual(tokens[1].value, "Hello World")

    def test_escaped_string(self):
        tokens = tokenize('LOG "line1\\nline2"')
        self.assertEqual(tokens[1].value, "line1\nline2")

    def test_comments_are_stripped(self):
        tokens = tokenize("LINK PIN 18 TO X # comment here\nLOG \"done\"")
        self.assertEqual(tokens[-1].kind, "STRING")

    def test_multiply_operator(self):
        tokens = tokenize('FORCE OVERRIDE BUFFER WITH "A" * 5000')
        kinds = [token.kind for token in tokens]
        self.assertIn("MUL", kinds)
        self.assertEqual(tokens[-1].value, 5000)

    def test_identifier_bound(self):
        with self.assertRaises(LexError) as ctx:
            tokenize(f"LINK PIN 18 TO {'X' * (IDENTIFIER_MAX + 1)}")
        self.assertIn("Buffer overflow", str(ctx.exception))

    def test_string_bound(self):
        payload = "A" * (STRING_MAX_BYTES + 1)
        with self.assertRaises(LexError) as ctx:
            tokenize(f'LOG "{payload}"')
        self.assertIn("Buffer overflow", str(ctx.exception))

    def test_unterminated_string(self):
        with self.assertRaises(LexError):
            tokenize('LOG "oops')

    def test_bad_character(self):
        with self.assertRaises(LexError):
            tokenize("LOG @")

    def test_line_tracking(self):
        tokens = tokenize("LINK PIN 18 TO X\nLINK PIN 19 TO Y\n")
        links = [token for token in tokens if token.kind == "LINK"]
        self.assertEqual([token.line for token in links], [1, 2])

    def test_new_keywords(self):
        tokens = tokenize("ATOMIC\nDELAY 500 MS\nAUTHENTICATE WITH \"0xDEAD\"\nEND\n")
        kinds = [token.kind for token in tokens]
        self.assertIn("ATOMIC", kinds)
        self.assertIn("DELAY", kinds)
        self.assertIn("MS", kinds)
        self.assertIn("AUTHENTICATE", kinds)
        self.assertIn("END", kinds)

    def test_control_flow_keywords(self):
        tokens = tokenize("REPEAT 3 TIMES WHILE HIGH EVERY 500 MS ANALOG_READ AS ANALOG")
        kinds = [token.kind for token in tokens]
        self.assertIn("REPEAT", kinds)
        self.assertIn("TIMES", kinds)
        self.assertIn("WHILE", kinds)
        self.assertIn("HIGH", kinds)
        self.assertIn("EVERY", kinds)
        self.assertIn("MS", kinds)
        self.assertIn("ANALOG_READ", kinds)
        self.assertIn("ANALOG", kinds)

    def test_line_and_column_tracking(self):
        tokens = tokenize("REPEAT 3 TIMES\n    LOG \"x\"\nEND")
        log = next(token for token in tokens if token.kind == "LOG")
        self.assertEqual(log.line, 2)
        self.assertEqual(log.column, 5)


if __name__ == "__main__":
    unittest.main()
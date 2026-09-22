import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.lexer import tokenize
from sentrypi.parser import Parser
from sentrypi.semantic_analyzer import SemanticAnalyzer


def warnings_of(source):
    program = Parser(tokenize(source)).parse_program()
    return SemanticAnalyzer().analyze(program)


class TestSemanticAnalyzer(unittest.TestCase):
    def test_clean_program_has_no_warnings(self):
        source = (
            "LINK PIN 18 TO ALARM AS OUTPUT\n"
            "LINK PIN 23 TO PIR AS INPUT\n"
            "IF PIR HIGH THEN\n"
            "    ALARM HIGH\n"
            "END\n"
            "ALARM LOW\n"
        )
        self.assertEqual(warnings_of(source), [])

    def test_unknown_component_is_warned(self):
        issues = warnings_of("ALARM HIGH")
        self.assertTrue(any(issue.severity == "WARN" for issue in issues))
        self.assertTrue(any("Unknown component 'ALARM'" in issue.message for issue in issues))

    def test_duplicate_link_is_warned(self):
        issues = warnings_of("LINK PIN 18 TO A AS OUTPUT\nLINK PIN 19 TO A AS OUTPUT")
        self.assertTrue(any("already linked" in issue.message for issue in issues))

    def test_duplicate_pin_is_warned(self):
        issues = warnings_of("LINK PIN 18 TO A AS OUTPUT\nLINK PIN 18 TO B AS INPUT")
        self.assertTrue(any("linked more than once" in issue.message for issue in issues))

    def test_unknown_condition_is_warned(self):
        issues = warnings_of("IF GHOST HIGH THEN\n    LOG \"x\"\nEND")
        self.assertTrue(any("Unknown condition" in issue.message for issue in issues) or
                        any("Unknown component 'GHOST'" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
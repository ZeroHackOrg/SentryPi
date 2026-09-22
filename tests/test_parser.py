import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.ast_nodes import (
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
from sentrypi.lexer import tokenize
from sentrypi.parser import Parser


def parse(source):
    return Parser(tokenize(source)).parse_program()


def parse_with_errors(source):
    parser = Parser(tokenize(source))
    program = parser.parse_program()
    return program, parser.errors


class TestParser(unittest.TestCase):
    def test_link_output(self):
        program = parse("LINK PIN 18 TO TARGET_LED AS OUTPUT")
        self.assertEqual(len(program.statements), 1)
        stmt = program.statements[0]
        self.assertIsInstance(stmt, LinkPin)
        self.assertEqual(stmt.pin, 18)
        self.assertEqual(stmt.target, "TARGET_LED")
        self.assertEqual(stmt.mode, "OUTPUT")

    def test_link_input(self):
        stmt = parse("LINK PIN 23 TO MOTION_SENSOR AS INPUT").statements[0]
        self.assertEqual(stmt.mode, "INPUT")

    def test_link_without_mode(self):
        stmt = parse("LINK PIN 02 TO SYSTEM_CLOCK").statements[0]
        self.assertIsNone(stmt.mode)

    def test_trigger(self):
        stmt = parse("TRIGGER TARGET_LED HIGH").statements[0]
        self.assertIsInstance(stmt, Trigger)
        self.assertEqual(stmt.target, "TARGET_LED")
        self.assertEqual(stmt.value, "HIGH")

    def test_assign(self):
        stmt = parse("ALARM HIGH").statements[0]
        self.assertIsInstance(stmt, Assign)
        self.assertEqual(stmt.target, "ALARM")
        self.assertEqual(stmt.value, "HIGH")

    def test_log(self):
        stmt = parse('LOG "Alert triggered."').statements[0]
        self.assertIsInstance(stmt, Log)
        self.assertEqual(stmt.message, "Alert triggered.")

    def test_if_block(self):
        program = parse(
            'IF MOTION_SENSOR IS HIGH THEN\n'
            '    TRIGGER TARGET_LED HIGH\n'
            'END\n'
        )
        stmt = program.statements[0]
        self.assertIsInstance(stmt, IfBlock)
        self.assertEqual(stmt.condition, "MOTION_SENSOR")
        self.assertEqual(stmt.state, "HIGH")
        self.assertEqual(len(stmt.body), 1)
        self.assertIsInstance(stmt.body[0], Trigger)

    def test_if_without_is(self):
        stmt = parse("IF MOTION_SENSOR LOW THEN\n    LOG \"ok\"\nEND").statements[0]
        self.assertIsInstance(stmt, IfBlock)
        self.assertEqual(stmt.state, "LOW")

    def test_force_override(self):
        stmt = parse('FORCE OVERRIDE BUFFER WITH "A" * 5000').statements[0]
        self.assertIsInstance(stmt, ForceOverride)
        self.assertEqual(stmt.target, "BUFFER")
        self.assertEqual(stmt.value, "A")
        self.assertEqual(stmt.count, 5000)

    def test_force_override_default_count(self):
        stmt = parse('FORCE OVERRIDE BUFFER WITH "payload"').statements[0]
        self.assertEqual(stmt.count, 1)

    def test_missing_output_mode(self):
        _, errors = parse_with_errors("LINK PIN 18 TO X AS HIGH")
        self.assertTrue(errors)
        self.assertEqual(errors[0].line, 1)

    def test_unclosed_if(self):
        _, errors = parse_with_errors("IF X IS HIGH THEN\n    LOG \"x\"\n")
        self.assertTrue(errors)

    def test_unknown_statement(self):
        _, errors = parse_with_errors("BANANA 42")
        self.assertTrue(errors)

    def test_panic_mode_recovers_multiple_errors(self):
        source = (
            "LINK PIN 18 TO A AS OUTPUT\n"
            "BANANA 1\n"
            "LINK PIN 19\n"
            "LINK PIN 23 TO B AS INPUT\n"
            "TRIGGER B HIGH\n"
        )
        _, errors = parse_with_errors(source)
        self.assertGreaterEqual(len(errors), 2)

    def test_valid_statements_survive_recovery(self):
        source = "BANANA 1\nLINK PIN 18 TO A AS OUTPUT\nQUARK 9\nLINK PIN 23 TO B AS INPUT\n"
        program, errors = parse_with_errors(source)
        self.assertGreaterEqual(len(errors), 2)
        self.assertEqual(len(program.statements), 2)

    def test_atomic_block(self):
        program = parse("ATOMIC\n    LOG \"x\"\nEND\n")
        stmt = program.statements[0]
        self.assertIsInstance(stmt, AtomicBlock)
        self.assertEqual(len(stmt.body), 1)

    def test_delay(self):
        stmt = parse("DELAY 500 MS").statements[0]
        self.assertIsInstance(stmt, Delay)
        self.assertEqual(stmt.ms, 500)

    def test_authenticate(self):
        stmt = parse('AUTHENTICATE WITH "0xDEADBEEF"').statements[0]
        self.assertIsInstance(stmt, Authenticate)
        self.assertEqual(stmt.signature, "0xDEADBEEF")

    def test_repeat_block(self):
        program = parse("REPEAT 3 TIMES\n    LOG \"tick\"\nEND\n")
        stmt = program.statements[0]
        self.assertIsInstance(stmt, RepeatBlock)
        self.assertEqual(stmt.count, 3)
        self.assertEqual(len(stmt.body), 1)
        self.assertIsInstance(stmt.body[0], Log)

    def test_unclosed_repeat(self):
        _, errors = parse_with_errors("REPEAT 2 TIMES\n    LOG \"x\"\n")
        self.assertTrue(errors)

    def test_while_block(self):
        stmt = parse("WHILE PIR IS HIGH\n    LOG \"x\"\nEND\n").statements[0]
        self.assertIsInstance(stmt, WhileBlock)
        self.assertEqual(stmt.condition, "PIR")
        self.assertEqual(stmt.state, "HIGH")

    def test_while_without_is(self):
        stmt = parse("WHILE PIR LOW\n    LOG \"x\"\nEND\n").statements[0]
        self.assertIsInstance(stmt, WhileBlock)
        self.assertEqual(stmt.state, "LOW")

    def test_every_block(self):
        stmt = parse("EVERY 500 MS\n    LOG \"heartbeat\"\nEND\n").statements[0]
        self.assertIsInstance(stmt, EveryBlock)
        self.assertEqual(stmt.ms, 500)

    def test_analog_read(self):
        stmt = parse("ANALOG_READ THERMISTOR").statements[0]
        self.assertIsInstance(stmt, AnalogRead)
        self.assertEqual(stmt.target, "THERMISTOR")

    def test_link_analog_mode(self):
        stmt = parse("LINK PIN 32 TO THERMISTOR AS ANALOG").statements[0]
        self.assertIsInstance(stmt, LinkPin)
        self.assertEqual(stmt.mode, "ANALOG")

    def test_nested_blocks(self):
        program = parse(
            "EVERY 500 MS\n"
            "    REPEAT 2 TIMES\n"
            "        WHILE PIR HIGH\n"
            "            LOG \"nested\"\n"
            "        END\n"
            "    END\n"
            "END\n"
        )
        every = program.statements[0]
        self.assertIsInstance(every.body[0], RepeatBlock)
        self.assertIsInstance(every.body[0].body[0], WhileBlock)


if __name__ == "__main__":
    unittest.main()
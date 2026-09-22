import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.ir import IRGenerator
from sentrypi.lexer import tokenize
from sentrypi.parser import Parser


def ir_of(source):
    program = Parser(tokenize(source)).parse_program()
    return IRGenerator().generate(program)


class TestIRGenerator(unittest.TestCase):
    def test_simple_program(self):
        tac = ir_of("LINK PIN 18 TO ALARM AS OUTPUT\nALARM HIGH\nLOG \"done\"\n")
        ops = [instruction["op"] for instruction in tac]
        self.assertEqual(ops, ["ALLOC_PIN", "MAP_ALIAS", "WRITE_BIT", "LOG"])

    def test_register_allocation(self):
        tac = ir_of("LINK PIN 18 TO ALARM AS OUTPUT\nALARM HIGH\n")
        alloc = tac[0]
        self.assertEqual(alloc["pin"], 18)
        self.assertEqual(alloc["mode"], "OUTPUT")
        self.assertEqual(alloc["reg"], "t0")

    def test_write_bit_value(self):
        tac = ir_of("LINK PIN 18 TO ALARM AS OUTPUT\nALARM HIGH\nALARM LOW\n")
        writes = [instruction for instruction in tac if instruction["op"] == "WRITE_BIT"]
        self.assertEqual([instruction["value"] for instruction in writes], [1, 0])

    def test_if_block_emits_branch_and_label(self):
        tac = ir_of(
            "LINK PIN 23 TO PIR AS INPUT\n"
            "LINK PIN 18 TO ALARM AS OUTPUT\n"
            "IF PIR HIGH THEN\n"
            "    ALARM HIGH\n"
            "END\n"
        )
        ops = [instruction["op"] for instruction in tac]
        self.assertIn("BRANCH", ops)
        self.assertIn("LABEL", ops)
        branch = next(instruction for instruction in tac if instruction["op"] == "BRANCH")
        labels = [instruction["name"] for instruction in tac if instruction["op"] == "LABEL"]
        self.assertIn(branch["label"], labels)

    def test_trigger_uses_alias_register(self):
        tac = ir_of("LINK PIN 18 TO LED AS OUTPUT\nTRIGGER LED HIGH\n")
        write = next(instruction for instruction in tac if instruction["op"] == "WRITE_BIT")
        self.assertEqual(write["reg"], "t0")

    def test_delay_emits_op(self):
        tac = ir_of("LINK PIN 18 TO LED AS OUTPUT\nLED HIGH\nDELAY 500 MS\n")
        delay = next(instruction for instruction in tac if instruction["op"] == "DELAY")
        self.assertEqual(delay["ms"], 500)

    def test_atomic_block_flattens_body(self):
        tac = ir_of(
            "LINK PIN 23 TO PIR AS INPUT\n"
            "LINK PIN 18 TO ALARM AS OUTPUT\n"
            "ATOMIC\n"
            "    IF PIR HIGH THEN\n"
            "        ALARM HIGH\n"
            "    END\n"
            "END\n"
        )
        ops = [instruction["op"] for instruction in tac]
        self.assertNotIn("ATOMIC", ops)
        self.assertIn("BRANCH", ops)
        self.assertIn("LABEL", ops)

    def test_authenticate_is_skipped(self):
        tac = ir_of('AUTHENTICATE WITH "0xABCDEF" \nLINK PIN 18 TO LED AS OUTPUT\nLED HIGH\n')
        self.assertTrue(all(instruction["op"] != "AUTHENTICATE" for instruction in tac))


if __name__ == "__main__":
    unittest.main()
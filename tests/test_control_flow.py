import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.ir import IRGenerator
from sentrypi.lexer import tokenize
from sentrypi.optimizer import optimize
from sentrypi.parser import Parser


def ir_of(source):
    program = Parser(tokenize(source)).parse_program()
    return IRGenerator().generate(program)


class TestIRControlFlow(unittest.TestCase):
    def test_repeat_emits_loop_and_jump(self):
        tac = ir_of(
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "REPEAT 4 TIMES\n"
            "    LED HIGH\n"
            "    LED LOW\n"
            "END\n"
        )
        ops = [instruction["op"] for instruction in tac]
        self.assertIn("LOOP", ops)
        self.assertIn("JUMP", ops)
        loop = next(instruction for instruction in tac if instruction["op"] == "LOOP")
        jump = next(instruction for instruction in tac if instruction["op"] == "JUMP")
        self.assertEqual(loop["count"], 4)
        self.assertEqual(jump["label"], loop["label"])

    def test_while_emits_cycle(self):
        tac = ir_of(
            "LINK PIN 23 TO PIR AS INPUT\n"
            "WHILE PIR IS HIGH\n"
            "    LOG \"guard\"\n"
            "END\n"
        )
        while_op = next(instruction for instruction in tac if instruction["op"] == "WHILE")
        jump = next(instruction for instruction in tac if instruction["op"] == "JUMP")
        alloc = next(instruction for instruction in tac if instruction["op"] == "ALLOC_PIN")
        self.assertEqual(while_op["value"], 1)
        self.assertEqual(while_op["reg"], alloc["reg"])
        self.assertEqual(jump["label"], while_op["label"])

    def test_every_emits_timer_and_cycle(self):
        tac = ir_of(
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "EVERY 500 MS\n"
            "    LED LOW\n"
            "END\n"
        )
        timer = next(instruction for instruction in tac if instruction["op"] == "TIMER")
        jump = next(instruction for instruction in tac if instruction["op"] == "JUMP")
        self.assertEqual(timer["ms"], 500)
        self.assertEqual(jump["label"], timer["label"])

    def test_analog_read_reuses_channel_register(self):
        tac = ir_of("LINK PIN 32 TO THERMISTOR AS ANALOG\nANALOG_READ THERMISTOR\n")
        alloc = next(instruction for instruction in tac if instruction["op"] == "ALLOC_PIN")
        read = next(instruction for instruction in tac if instruction["op"] == "ANALOG_READ")
        self.assertEqual(alloc["mode"], "ANALOG")
        self.assertEqual(read["reg"], alloc["reg"])


class TestOptimizerLoop(unittest.TestCase):
    def test_write_not_folded_across_control_op(self):
        tac = [
            {"op": "WRITE_BIT", "reg": "t0", "value": 1},
            {"op": "WHILE", "reg": "t1", "value": 1, "label": "L0"},
            {"op": "WRITE_BIT", "reg": "t0", "value": 1},
            {"op": "JUMP", "label": "L0"},
        ]
        optimized, removed = optimize(tac)
        self.assertEqual(removed, 0)
        self.assertEqual([instruction["op"] for instruction in optimized], ["WRITE_BIT", "WHILE", "WRITE_BIT", "JUMP"])

    def test_loop_ops_preserved(self):
        tac = [{"op": "LOOP", "count": 3, "label": "L0", "reg": "t0"}, {"op": "JUMP", "label": "L0"}]
        optimized, removed = optimize(tac)
        self.assertEqual(removed, 0)
        self.assertEqual(optimized, tac)


if __name__ == "__main__":
    unittest.main()
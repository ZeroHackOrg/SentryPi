import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi import targets as target_registry
from sentrypi.compiler import compile_text
from sentrypi.lexer import tokenize
from sentrypi.parser import Parser
from sentrypi.target_esp32 import PHYSICAL_TO_GPIO, synthesize_ino, synthesize_llvm


def program_of(source):
    return Parser(tokenize(source)).parse_program()


class TestEsp32Target(unittest.TestCase):
    def test_esp32_is_registered(self):
        self.assertIn("esp32", target_registry.TARGETS)
        target = target_registry.get("esp32")
        self.assertTrue(target.emits_ino)
        self.assertTrue(target.emits_ll)
        self.assertFalse(target.emits_bin)
        self.assertFalse(target.emits_sh)
        self.assertFalse(target.emits_driver)

    def test_physical_mapping(self):
        self.assertEqual(PHYSICAL_TO_GPIO[18], 4)
        self.assertEqual(PHYSICAL_TO_GPIO[23], 19)

    def test_ino_contains_loop_constructs(self):
        source = (
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "REPEAT 3 TIMES\n"
            "    LED HIGH\n"
            "    DELAY 100 MS\n"
            "    LED LOW\n"
            "END\n"
        )
        sketch = synthesize_ino(program_of(source))
        self.assertIn("for (int __iter = 0; __iter < 3; __iter++)", sketch)
        self.assertIn("delay(100);", sketch)
        self.assertIn("void loop()", sketch)

    def test_ino_contains_while_and_timer(self):
        source = (
            "LINK PIN 23 TO PIR AS INPUT\n"
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "WHILE PIR IS HIGH\n"
            "    LED HIGH\n"
            "END\n"
            "EVERY 500 MS\n"
            "    LED LOW\n"
            "END\n"
        )
        sketch = synthesize_ino(program_of(source))
        self.assertIn("while (digitalRead(PIN_PIR) == HIGH)", sketch)
        self.assertIn("while (true)", sketch)
        self.assertIn("delay(500);", sketch)

    def test_ino_contains_analog_sampling(self):
        source = (
            "LINK PIN 32 TO THERMISTOR AS ANALOG\n"
            "ANALOG_READ THERMISTOR\n"
        )
        sketch = synthesize_ino(program_of(source))
        self.assertIn("pinMode(PIN_THERMISTOR, INPUT)", sketch)
        self.assertIn("analogRead(PIN_THERMISTOR)", sketch)

    def test_llvm_dump_shape(self):
        source = (
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "LED HIGH\n"
        )
        dump = synthesize_llvm(program_of(source))
        self.assertIn("define void @sentry_main()", dump)
        self.assertIn("call void @llvm.sentry.gpio.write", dump)

    def test_compile_selected_via_env(self):
        source = (
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "EVERY 1000 MS\n"
            "    LED HIGH\n"
            "END\n"
        )
        old = os.environ.pop("SENTRYPI_TARGET", None)
        try:
            os.environ["SENTRYPI_TARGET"] = "esp32"
            with tempfile.TemporaryDirectory() as tmp:
                result = compile_text(source, output_dir=tmp, name="esp_blink")
                self.assertTrue(result.ok)
                self.assertEqual(result.target_id, "esp32")
                self.assertIsNone(result.bin_path)
                self.assertIsNone(result.sh_path)
                self.assertTrue(result.ino_path.endswith("esp_blink.ino"))
                self.assertTrue(result.ll_path.endswith("esp_blink.ll"))
                self.assertTrue(result.map_path.endswith("esp_blink.map"))
        finally:
            os.environ.pop("SENTRYPI_TARGET", None)
            if old is not None:
                os.environ["SENTRYPI_TARGET"] = old


if __name__ == "__main__":
    unittest.main()
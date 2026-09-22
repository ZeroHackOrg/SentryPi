import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.lexer import tokenize
from sentrypi.parser import Parser
from sentrypi.static_analyzer import analyze


def firewall(source):
    program = Parser(tokenize(source)).parse_program()
    return analyze(program)


def errors_of(source):
    return [issue for issue in firewall(source) if issue.severity == "ERROR"]


def errors_of_hard(source):
    program = Parser(tokenize(source)).parse_program()
    return [issue for issue in analyze(program, hard=True) if issue.severity == "ERROR"]


class TestSecurityFirewall(unittest.TestCase):
    def test_alarm_passes(self):
        source = (
            "LINK PIN 18 TO TARGET_LED AS OUTPUT\n"
            "LINK PIN 23 TO MOTION_SENSOR AS INPUT\n"
            "IF MOTION_SENSOR IS HIGH THEN\n"
            "    TRIGGER TARGET_LED HIGH\n"
            "    LOG \"Alert.\"\n"
            "END\n"
        )
        self.assertEqual(errors_of(source), [])

    def test_reserved_pin_hijack_blocked(self):
        issues = firewall("LINK PIN 02 TO SYSTEM_CLOCK")
        messages = [issue.message for issue in issues]
        self.assertTrue(any("Reserved Pin 02" in message for message in messages))

    def test_buffer_overflow_detected(self):
        issues = firewall('FORCE OVERRIDE BUFFER WITH "A" * 5000')
        self.assertTrue(
            any("Buffer overflow" in issue.message for issue in issues if issue.severity == "ERROR")
        )
        self.assertTrue(any("5000 bytes" in issue.message for issue in issues))

    def test_security_vector_is_fully_blocked(self):
        source = "LINK PIN 02 TO SYSTEM_CLOCK\nFORCE OVERRIDE BUFFER WITH \"A\" * 5000\n"
        errors = errors_of(source)
        self.assertEqual(len(errors), 2)
        self.assertEqual(sorted(error.line for error in errors), [1, 2])

    def test_overflow_boundary_by_expansion(self):
        self.assertEqual(errors_of('FORCE OVERRIDE BUFFER WITH "X" * 256'), [])
        self.assertTrue(errors_of('FORCE OVERRIDE BUFFER WITH "X" * 257'))

    def test_write_to_input_is_rejected(self):
        source = "LINK PIN 23 TO MOTION_SENSOR AS INPUT\nTRIGGER MOTION_SENSOR HIGH\n"
        errors = errors_of(source)
        self.assertTrue(any("INPUT peripheral" in error.message for error in errors))

    def test_invalid_pin_is_error(self):
        errors = errors_of("LINK PIN 99 TO SOMETHING AS OUTPUT")
        self.assertTrue(errors)
        self.assertTrue(any("Invalid Pin 99" in error.message for error in errors))

    def test_protected_resource_write_blocked(self):
        errors = errors_of('FORCE OVERRIDE SYSTEM_CLOCK WITH "junk"')
        self.assertTrue(any("protected system resource" in error.message for error in errors))

    def test_atomic_block_mask_prevents_toctou(self):
        source = (
            "LINK PIN 23 TO PIR AS INPUT\n"
            "LINK PIN 18 TO ALARM AS OUTPUT\n"
            "ATOMIC\n"
            "    IF PIR HIGH THEN\n"
            "        ALARM HIGH\n"
            "    END\n"
            "END\n"
        )
        messages = [issue.message for issue in firewall(source)]
        self.assertFalse(any("TOCTOU" in message for message in messages))

    def test_unaligned_if_triggers_toctou_warning(self):
        source = (
            "LINK PIN 23 TO PIR AS INPUT\n"
            "LINK PIN 18 TO ALARM AS OUTPUT\n"
            "IF PIR HIGH THEN\n"
            "    ALARM HIGH\n"
            "END\n"
        )
        issues = firewall(source)
        self.assertTrue(any("TOCTOU" in issue.message for issue in issues))
        self.assertFalse(errors_of_hard(source) and len(errors_of(source)) > 0)

    def test_toctou_escalates_to_error_in_hard_mode(self):
        source = (
            "LINK PIN 23 TO PIR AS INPUT\n"
            "LINK PIN 18 TO ALARM AS OUTPUT\n"
            "IF PIR HIGH THEN\n"
            "    ALARM HIGH\n"
            "END\n"
        )
        self.assertEqual(len(errors_of(source)), 0)
        errors = errors_of_hard(source)
        self.assertEqual(len(errors), 1)
        self.assertTrue(any("TOCTOU" in error.message for error in errors))

    def test_toggle_overload_warning_and_hard_rejection(self):
        source = "LINK PIN 18 TO LED AS OUTPUT\n" + "LED HIGH\nLED LOW\n" * 13
        issues = firewall(source)
        warnings = [issue for issue in issues if issue.severity == "WARN"]
        self.assertTrue(any("toggle" in warning.message or "overload" in warning.message for warning in warnings))
        self.assertEqual(len(errors_of_hard(source)), 1)

    def test_delay_resets_overload_counter(self):
        source = "LINK PIN 18 TO LED AS OUTPUT\n" + "LED HIGH\nLED LOW\n" * 9 + "DELAY 2000 MS\n" + "LED HIGH\nLED LOW\n" * 9
        self.assertEqual(len(errors_of_hard(source)), 0)

    def test_analog_read_requires_analog_channel(self):
        source = "LINK PIN 18 TO THERMISTOR AS OUTPUT\nANALOG_READ THERMISTOR\n"
        errors = errors_of(source)
        self.assertTrue(any("ANALOG_READ" in error.message for error in errors))
        self.assertTrue(any("AS ANALOG" in error.message for error in errors))
        safe = "LINK PIN 32 TO THERMISTOR AS ANALOG\nANALOG_READ THERMISTOR\n"
        self.assertEqual(errors_of(safe), [])

    def test_analog_write_is_rejected(self):
        errors = errors_of("LINK PIN 32 TO THERMISTOR AS ANALOG\nTHERMISTOR HIGH\n")
        self.assertTrue(any("analog sensor channel" in error.message for error in errors))
        self.assertTrue(all(error.severity == "ERROR" for error in errors))

    def test_while_poll_triggers_toctou_warning(self):
        source = (
            "LINK PIN 23 TO PIR AS INPUT\n"
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "WHILE PIR IS HIGH\n"
            "    LED HIGH\n"
            "END\n"
        )
        issues = firewall(source)
        self.assertTrue(any("TOCTOU" in issue.message for issue in issues))
        self.assertEqual(len(errors_of_hard(source)), 1)

    def test_while_wrapped_in_atomic_is_clean(self):
        source = (
            "LINK PIN 23 TO PIR AS INPUT\n"
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "ATOMIC\n"
            "    WHILE PIR IS HIGH\n"
            "        LED HIGH\n"
            "    END\n"
            "END\n"
        )
        messages = [issue.message for issue in firewall(source)]
        self.assertFalse(any("TOCTOU" in message for message in messages))

    def test_repeat_loop_overload_warns_and_escalates(self):
        source = (
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "REPEAT 13 TIMES\n"
            "    LED HIGH\n"
            "    LED LOW\n"
            "END\n"
        )
        issues = firewall(source)
        self.assertTrue(
            any("overload" in issue.message or "toggles" in issue.message for issue in issues)
        )
        self.assertEqual(len(errors_of_hard(source)), 1)

    def test_repeat_with_delay_barrier_is_clean(self):
        source = (
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "REPEAT 100 TIMES\n"
            "    LED HIGH\n"
            "    DELAY 10 MS\n"
            "    LED LOW\n"
            "END\n"
        )
        self.assertEqual(errors_of_hard(source), [])

    def test_repeat_bound_exceeded_warns(self):
        source = "LINK PIN 18 TO LED AS OUTPUT\nREPEAT 2000000 TIMES\n    LED HIGH\nEND\n"
        issues = firewall(source)
        self.assertTrue(any("Loop bound" in issue.message for issue in issues))
        self.assertGreaterEqual(len(errors_of_hard(source)), 1)

    def test_every_zero_interval_warns(self):
        source = "LINK PIN 18 TO LED AS OUTPUT\nEVERY 0 MS\n    LED LOW\nEND\n"
        issues = firewall(source)
        self.assertTrue(any("busy-waits" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
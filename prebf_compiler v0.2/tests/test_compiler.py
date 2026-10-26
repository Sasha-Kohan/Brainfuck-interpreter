import unittest

from prebf.compiler import compile_source
from prebf.errors import PreBFError
from tests.bf_runner import run_bf


class CompilerTests(unittest.TestCase):
    def run_source(self, source: str, input_text: str = "", logical_bits: int = 8) -> str:
        bf = compile_source(source, bits=logical_bits)
        # The backend always targets ordinary wrapping 8-bit BF tape cells;
        # logical integers wider than one byte occupy several tape cells.
        return run_bf(bf, input_text=input_text, bits=8, step_limit=100_000_000)

    def test_print_without_parentheses(self):
        self.assertEqual(self.run_source("new a\na := 67\nprint a\n"), "67\n")

    def test_legacy_output_spelling_remains_accepted(self):
        self.assertEqual(self.run_source("new a\na := 67\noutput(a)\n"), "67\n")

    def test_input_addition_and_else(self):
        source = """new a
new b
new c
input a
input b
c := a + b
print c
if a == b
\tprint a
else
\tprint b
"""
        self.assertEqual(self.run_source(source, "12 30\n"), "42\n30\n")

    def test_negative_input_and_subtraction(self):
        source = """new a
new b
new c
input a
input b
c := a - b
print c
"""
        self.assertEqual(self.run_source(source, "-8 3\n"), "-11\n")

    def test_minimum_signed_8_bit_value(self):
        self.assertEqual(self.run_source("new a\na := -128\nprint a\n"), "-128\n")

    def test_wraparound_and_signed_output(self):
        source = "new a\na := 127\na := a + a\nprint a\n"
        self.assertEqual(self.run_source(source), "-2\n")

    def test_if_equal_branch(self):
        source = """new a
new b
input a
input b
if a == b
\tprint a
else
\tprint b
"""
        self.assertEqual(self.run_source(source, "5 5\n"), "5\n")
        self.assertEqual(self.run_source(source, "5 6\n"), "6\n")

    def test_target_can_alias_source(self):
        source = """new a
new b
a := 7
b := 4
a := a + b
print a
a := a - b
print a
"""
        self.assertEqual(self.run_source(source), "11\n7\n")

    def test_16_bit_signed_boundaries_and_arithmetic(self):
        source = """new a
new b
new c
a := 32767
print a
a := -32768
print a
b := 30000
c := 10000
a := b + c
print a
a := b - c
print a
"""
        self.assertEqual(self.run_source(source, logical_bits=16), "32767\n-32768\n-25536\n20000\n")

    def test_16_bit_input_is_signed(self):
        self.assertEqual(self.run_source("new a\ninput a\nprint a\n", "-32768\n", logical_bits=16), "-32768\n")
        self.assertEqual(self.run_source("new a\ninput a\nprint a\n", "12345\n", logical_bits=16), "12345\n")

    def test_12_bit_width_masks_unused_high_bits(self):
        source = """new a
new one
a := 2047
one := 1
a := a + one
print a
new b
b := -2048
print b
"""
        self.assertEqual(self.run_source(source, logical_bits=12), "-2048\n-2048\n")

    def test_32_bit_signed_boundaries_and_input(self):
        source = """new a
a := 2147483647
print a
a := -2147483648
print a
input a
print a
"""
        self.assertEqual(
            self.run_source(source, "123456789\n", logical_bits=32),
            "2147483647\n-2147483648\n123456789\n",
        )

    def test_arithmetic_can_overflow_at_configured_width(self):
        source = """new a
new one
a := 2147483647
one := 1
a := a + one
print a
"""
        self.assertEqual(self.run_source(source, logical_bits=32), "-2147483648\n")

    def test_non_positive_bit_width_is_rejected(self):
        for width in (0, -1):
            with self.assertRaises(ValueError):
                compile_source("new a\n", bits=width)


if __name__ == "__main__":
    unittest.main()

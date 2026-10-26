import unittest

from prebf.compiler import compile_source
from prebf.errors import PreBFError
from tests.bf_runner import run_bf


class CompilerTests(unittest.TestCase):
    def run_source(self, source: str, input_text: str = "") -> str:
        bf = compile_source(source, bits=8)
        return run_bf(bf, input_text=input_text, bits=8)

    def test_constant_and_output(self):
        self.assertEqual(self.run_source("new a\na := 67\noutput(a)\n"), "67\n")

    def test_input_addition_and_else(self):
        source = """new a
new b
new c
input a
input b
c := a + b
output(c)
if a == b
\toutput(a)
else
\toutput(b)
"""
        self.assertEqual(self.run_source(source, "12 30\n"), "42\n30\n")

    def test_negative_input_and_subtraction(self):
        source = """new a
new b
new c
input a
input b
c := a - b
output(c)
"""
        self.assertEqual(self.run_source(source, "-8 3\n"), "-11\n")

    def test_minimum_signed_value(self):
        source = "new a\na := -128\noutput(a)\n"
        self.assertEqual(self.run_source(source), "-128\n")

    def test_wraparound_and_signed_output(self):
        source = "new a\na := 127\na := a + a\noutput(a)\n"
        self.assertEqual(self.run_source(source), "-2\n")

    def test_if_equal_branch(self):
        source = """new a
new b
input a
input b
if a == b
\toutput(a)
else
\toutput(b)
"""
        self.assertEqual(self.run_source(source, "5 5\n"), "5\n")

    def test_target_can_alias_source(self):
        source = """new a
new b
a := 7
b := 4
a := a + b
output(a)
a := a - b
output(a)
"""
        self.assertEqual(self.run_source(source), "11\n7\n")

    def test_invalid_bit_width_is_rejected(self):
        with self.assertRaises(ValueError):
            compile_source("new a\n", bits=12)


if __name__ == "__main__":
    unittest.main()

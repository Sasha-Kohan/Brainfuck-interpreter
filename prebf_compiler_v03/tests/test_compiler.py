import unittest

from prebf.compiler import compile_source
from tests.bf_runner import run_bf


class CompilerTests(unittest.TestCase):
    def run_source(self, source: str, input_text: str = "", logical_bits: int = 8) -> str:
        bf = compile_source(source, bits=logical_bits)
        return run_bf(bf, input_text=input_text, bits=8, step_limit=100_000_000)

    def test_assignment_uses_equal_sign(self):
        self.assertEqual(self.run_source("new a = 42\nprint a\n"), "42\n")

    def test_legacy_assignment_and_output_remain_accepted(self):
        self.assertEqual(self.run_source("new a\na := 67\noutput(a)\n"), "67\n")

    def test_arithmetic_expressions_and_precedence(self):
        source = """new a = 3
new b = 4
new c = a + b + a
print c
new d = 16*a+b
print d
new e = -a+b+b
print e
new f = (a+b)*2
print f
"""
        self.assertEqual(self.run_source(source), "10\n52\n5\n14\n")

    def test_initializer_can_reference_its_zero_initialized_variable(self):
        # b must be declared before it is referenced; the new a is zero while
        # its initializer is evaluated.
        source = """new b = 7
new a = 16*a+b
print a
"""
        self.assertEqual(self.run_source(source), "7\n")

    def test_initializer_and_assignment_support_multiplication(self):
        source = """new b = 7
new a = 16*a+b
new c = a*3
print a
print c
"""
        self.assertEqual(self.run_source(source), "7\n21\n")

    def test_input_addition_and_else_if(self):
        source = """new a
new b
new c
input a
input b
c = a + b
print c
if a == b:
	print a
else if a < b:
	print a
else:
	print b
"""
        self.assertEqual(self.run_source(source, "12 30\n"), "42\n12\n")
        self.assertEqual(self.run_source(source, "9 9\n"), "18\n9\n")
        self.assertEqual(self.run_source(source, "30 12\n"), "42\n12\n")

    def test_signed_conditions(self):
        for op, a, b, expected in [
            ("<", -5, 2, -5), ("<", 4, 2, 2), ("<=", 2, 2, 2),
            (">", 4, -2, 4), (">=", -1, 0, 0), ("!=", 7, 9, 7),
            ("==", 7, 9, 9),
        ]:
            source = f"new a = {a}\nnew b = {b}\nif a {op} b:\n\tprint a\nelse:\n\tprint b\n"
            self.assertEqual(self.run_source(source), f"{expected}\n", (op, a, b))

    def test_while_loop(self):
        source = """new i = 0
new total = 0
while i < 4:
	 total = total + i
	 i++
print total
print i
""".replace("\t ", "\t")
        self.assertEqual(self.run_source(source), "6\n4\n")

    def test_for_loop_with_postfix_increment(self):
        source = """new sum = 0
for (new i = 0; i < 5; i++):
	sum = sum + i
print sum
"""
        self.assertEqual(self.run_source(source), "10\n")

    def test_for_loop_with_assignment_update_and_nested_while(self):
        source = """new sum = 0
new i = 0
for (i = 0; i < 3; i = i + 1):
	new j = 0
	while j < 2:
		sum = sum + 1
		j += 1
print sum
"""
        self.assertEqual(self.run_source(source), "6\n")

    def test_empty_loop_body_and_else_branch(self):
        source = """new a = 1
while a < 1:
if a == 0:
else:
	print a
"""
        self.assertEqual(self.run_source(source), "1\n")

    def test_negative_input_and_subtraction(self):
        source = """new a
new b
new c
input a
input b
c = a - b
print c
"""
        self.assertEqual(self.run_source(source, "-8 3\n"), "-11\n")

    def test_minimum_signed_8_bit_value(self):
        self.assertEqual(self.run_source("new a = -128\nprint a\n"), "-128\n")

    def test_16_bit_signed_boundaries_and_arithmetic(self):
        source = """new a = 32767
print a
a = -32768
print a
new b = 30000
new c = 10000
a = b + c
print a
a = b - c
print a
"""
        self.assertEqual(self.run_source(source, logical_bits=16), "32767\n-32768\n-25536\n20000\n")

    def test_16_bit_multiplication_and_comparison(self):
        source = """new a = 200
new b = 200
new c = a*b
print c
new low = -12000
new high = 1000
if low < high:
	print low
else:
	print high
"""
        self.assertEqual(self.run_source(source, logical_bits=16), "-25536\n-12000\n")

    def test_conditions_can_contain_expressions(self):
        source = """new a = 3
new b = 2
if (a + 2) < (b * 3):
	print a
else:
	print b
"""
        self.assertEqual(self.run_source(source), "3\n")

    def test_16_bit_input_is_signed(self):
        self.assertEqual(self.run_source("new a\ninput a\nprint a\n", "-32768\n", 16), "-32768\n")
        self.assertEqual(self.run_source("new a\ninput a\nprint a\n", "12345\n", 16), "12345\n")

    def test_12_bit_width_masks_unused_high_bits(self):
        source = """new a = 2047
new one = 1
a = a + one
print a
new b = -2048
print b
"""
        self.assertEqual(self.run_source(source, logical_bits=12), "-2048\n-2048\n")

    def test_32_bit_signed_boundaries_and_input(self):
        source = """new a = 2147483647
print a
a = -2147483648
print a
input a
print a
"""
        self.assertEqual(self.run_source(source, "123456789\n", 32), "2147483647\n-2147483648\n123456789\n")

    def test_arithmetic_can_overflow_at_configured_width(self):
        source = """new a = 2147483647
new one = 1
a = a + one
print a
"""
        self.assertEqual(self.run_source(source, logical_bits=32), "-2147483648\n")

    def test_non_positive_bit_width_is_rejected(self):
        for width in (0, -1):
            with self.assertRaises(ValueError):
                compile_source("new a\n", bits=width)


if __name__ == "__main__":
    unittest.main()

import unittest

from prebf.compiler import compile_source
from prebf.errors import PreBFError
from tests.bf_runner import run_bf


class TypeSystemTests(unittest.TestCase):
    def run_source(self, source: str, input_text: str = "", bits: int = 8, capacity: int = 8) -> str:
        code = compile_source(source, bits=bits, max_array_size=capacity)
        return run_bf(code, input_text, bits=8, step_limit=100_000_000)

    def test_typed_scalar_initializers_and_comma_declarations(self):
        source = """new int a = 6, b = 7, c = a + b
print a
print b
print c
"""
        self.assertEqual(self.run_source(source), "6\n7\n13\n")

    def test_bool_can_be_initialized_from_comparison(self):
        source = """new int a = 5
new int b = 5
new bool t = a == b
new bool f = a != b
print t
print f
"""
        self.assertEqual(self.run_source(source), "1\n0\n")

    def test_bool_converts_nonzero_numeric_to_one(self):
        source = """new int a = -9
new bool t = a
new bool f = 0
print t
print f
"""
        self.assertEqual(self.run_source(source), "1\n0\n")

    def test_char_literal_prints_a_character(self):
        self.assertEqual(self.run_source("new char c = 'R'\nprint c\n"), "R\n")

    def test_char_conversion_keeps_low_eight_bits(self):
        self.assertEqual(self.run_source("new char c = 300\nprint c\n", bits=16), ",\n")

    def test_char_input_skips_whitespace(self):
        self.assertEqual(self.run_source("new char c\ninput c\nprint c\n", "  \nZ"), "Z\n")

    def test_pair_initializer_and_fields(self):
        source = """new pair<int, char> p = {67, 'Y'}
print p.first
print p.second
p.first = 12
p.second = 'Q'
print p.first
print p.second
"""
        self.assertEqual(self.run_source(source), "67\nY\n12\nQ\n")

    def test_array_element_assignment_read_and_size(self):
        source = """new int a[6]
a[5] = 42
new int b = a[5]
print b
print a.size()
"""
        self.assertEqual(self.run_source(source), "42\n6\n")

    def test_dynamic_array_size_from_variable(self):
        source = """new int n = 6
new int a[n]
a[5] = 19
new int b = a[5]
print b
print a.size()
"""
        self.assertEqual(self.run_source(source, capacity=8), "19\n6\n")

    def test_dynamic_array_size_is_clamped_to_reserved_capacity(self):
        source = """new int n = 20
new int a[n]
print a.size()
"""
        self.assertEqual(self.run_source(source, capacity=4), "4\n")

    def test_runtime_indexing_reads_and_writes_elements(self):
        source = """new int a[4]
new int i = 2
a[i] = 24
new int b = a[i]
print b
"""
        self.assertEqual(self.run_source(source, capacity=4), "24\n")

    def test_dynamic_sized_array_literal_index_checks_runtime_size(self):
        source = """new int n = 2
new int a[n]
a[5] = 19
new int b = a[5]
print b
"""
        self.assertEqual(self.run_source(source, capacity=8), "0\n")

    def test_pair_array(self):
        source = """new pair<int, char> p[3]
p[1].first = 12
p[1].second = 'Q'
print p[1].first
print p[1].second
print p.size()
"""
        self.assertEqual(self.run_source(source, capacity=4), "12\nQ\n3\n")

    def test_array_input_uses_element_type(self):
        source = """new char str[4]
input str[1]
print str[1]
"""
        self.assertEqual(self.run_source(source, "Z"), "Z\n")

    def test_array_access_in_if_condition(self):
        source = """new int a[4]
new int i = 2
a[2] = 9
if a[i] == 9:
	print a[i]
else:
	print 0
"""
        self.assertEqual(self.run_source(source, capacity=4), "9\n")

    def test_array_out_of_bounds_static_index_is_error(self):
        with self.assertRaises(PreBFError):
            compile_source("new int a[2]\nprint a[2]\n")

    def test_read_only_size_cannot_be_input_target(self):
        with self.assertRaises(PreBFError):
            compile_source("new int a[2]\ninput a.size()\n")


    def test_typed_for_initializer(self):
        source = """new int sum = 0
for (new int i = 0; i < 3; i++):
	sum += i
print sum
"""
        self.assertEqual(self.run_source(source), "3\n")

    def test_comma_declarations_with_comparison_initializers(self):
        source = """new int a = 4, b = 9
new bool less = a < b, greater = b < a
print less
print greater
"""
        self.assertEqual(self.run_source(source), "1\n0\n")

    def test_dynamic_index_can_use_an_expression(self):
        source = """new int a[4]
a[2] = 77
new int i = 1
new int x = a[i + 1]
print x
"""
        self.assertEqual(self.run_source(source, capacity=4), "77\n")

    def test_character_type_requires_at_least_eight_integer_bits(self):
        with self.assertRaisesRegex(ValueError, "char requires"):
            compile_source("new char c = 'A'\n", bits=4)


    def test_trailing_comments_and_uninitialized_comma_declarators(self):
        source = """new int a = 6, b = 7, c // all three are declared
c = a + b
print c
"""
        self.assertEqual(self.run_source(source), "13\n")

    def test_unsupported_type_reports_a_clear_error(self):
        with self.assertRaisesRegex(PreBFError, "Unknown type"):
            compile_source("new float f = 1\n")

    def test_negative_dynamic_array_size_is_clamped_to_zero(self):
        source = """new int n = -2
new int a[n]
print a.size()
"""
        self.assertEqual(self.run_source(source, capacity=4), "0\n")

    def test_legacy_untyped_declarations_still_work(self):
        self.assertEqual(self.run_source("new a = 5\na = a + 2\nprint a\n"), "7\n")


if __name__ == "__main__":
    unittest.main()

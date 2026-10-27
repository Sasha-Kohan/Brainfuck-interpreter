import unittest

from prebf.ast import For, If, New, While
from prebf.errors import PreBFError
from prebf.parser import parse
from prebf.semantics import validate


class ParserTests(unittest.TestCase):
    def test_parses_nested_if_else_if_and_empty_branch(self):
        program = parse("""new a = 1
if a == 1:
	if a != 0:
	else:
		print a
else if a < 0:
	print a
else:
""")
        outer = program.statements[1]
        self.assertIsInstance(outer, If)
        self.assertEqual(len(outer.branches), 3)
        self.assertIsInstance(outer.branches[0].body[0], If)
        self.assertEqual(outer.branches[2].body, [])

    def test_parses_while_and_for_headers(self):
        program = parse("""new i = 0
while i < 3:
	i++
for (i = 0; i < 4; i = i + 1):
	print i
""")
        self.assertIsInstance(program.statements[1], While)
        self.assertIsInstance(program.statements[2], For)

    def test_comments_only_at_column_one(self):
        program = parse("// comment\nnew a\n")
        self.assertIsInstance(program.statements[0], New)
        with self.assertRaises(PreBFError):
            parse("\t// not a column-one comment\n")

    def test_spaces_are_rejected_for_indentation(self):
        with self.assertRaisesRegex(PreBFError, "табуляцию"):
            parse("new a\nif a == a:\n    print a\n")

    def test_unknown_instruction_is_rejected(self):
        with self.assertRaises(PreBFError):
            parse("dance a\n")

    def test_undeclared_variables_are_rejected(self):
        program = parse("new a\na = b + a\n")
        with self.assertRaisesRegex(PreBFError, "не объявлена"):
            validate(program)

    def test_duplicate_declarations_are_rejected(self):
        program = parse("new a\nnew a\n")
        with self.assertRaisesRegex(PreBFError, "повторно"):
            validate(program)

    def test_new_initializer_self_reference_is_declared_first(self):
        program = parse("new b = 7\nnew a = 16*a+b\n")
        self.assertEqual(validate(program), ["b", "a"])

    def test_missing_colon_in_control_header_is_rejected(self):
        with self.assertRaises(PreBFError):
            parse("new a = 1\nif a == 1\n\tprint a\n")


if __name__ == "__main__":
    unittest.main()

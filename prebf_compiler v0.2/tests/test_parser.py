import unittest

from prebf.ast import If, New
from prebf.errors import PreBFError
from prebf.parser import parse
from prebf.semantics import validate


class ParserTests(unittest.TestCase):
    def test_parses_nested_if_else_and_empty_block(self):
        program = parse("""new a
new b
if a == b
	if a == b
	else
		output(a)
else
""")
        outer = program.statements[2]
        self.assertIsInstance(outer, If)
        self.assertEqual(len(outer.then_body), 1)
        self.assertEqual(outer.else_body, [])
        inner = outer.then_body[0]
        self.assertIsInstance(inner, If)
        self.assertEqual(inner.then_body, [])
        self.assertIsNotNone(inner.else_body)
        self.assertEqual(inner.else_body[0].name, "a")

    def test_comments_only_at_column_one(self):
        program = parse("// full-line comment\nnew a\n")
        self.assertIsInstance(program.statements[0], New)
        with self.assertRaises(PreBFError):
            parse("\t// not a column-one comment\n")

    def test_spaces_are_rejected_for_indentation(self):
        with self.assertRaisesRegex(PreBFError, "табуляцию"):
            parse("new a\nif a == a\n    output(a)\n")

    def test_unknown_instruction_is_rejected(self):
        with self.assertRaises(PreBFError):
            parse("dance a\n")

    def test_undeclared_variables_are_rejected(self):
        program = parse("new a\na := b + a\n")
        with self.assertRaisesRegex(PreBFError, "не объявлена"):
            validate(program)

    def test_duplicate_declarations_are_rejected(self):
        program = parse("new a\nnew a\n")
        with self.assertRaisesRegex(PreBFError, "повторно"):
            validate(program)


if __name__ == "__main__":
    unittest.main()

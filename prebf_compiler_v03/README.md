# preBF compiler v0.3

A modular compiler for a small assembly-like language. It reads `program.prebf`, validates the program, and generates plain Brainfuck in `program.bf`. The project uses Python 3.10+ and has no third-party runtime dependencies.

## Quick start

```bash
python main.py
```

This compiles `program.prebf` to `program.bf` using signed 8-bit logical integers. Select any positive logical width; values are represented across multiple ordinary 8-bit Brainfuck cells using 4-bit limbs:

```bash
python main.py --bits 8
python main.py --bits 12
python main.py --bits 16
python main.py --bits 32
python main.py --bits 64
```

You can also choose files explicitly:

```bash
python main.py --input examples/arithmetic.prebf --output arithmetic.bf --bits 16
```

The generated code targets Brainfuck interpreters with wrapping 8-bit cells. Logical integer operations wrap modulo `2**bits` and use signed two's-complement representation. For example, a 16-bit integer ranges from `-32768` through `32767`; adding one to `32767` produces `-32768`.

## Language syntax

### Variables and expressions

```text
new a
new b = 7
new c = 16*a + b
c = a + b + c
c = -a + b + 2
c = (a + b) * 3
input a
print c
```

- `new name` declares a variable and initializes it to zero.
- `new name = expression` declares and initializes a variable. The new variable is zero before its initializer is evaluated, so `new a = 16*a+b` reads zero for the new `a`; `b` must already have been declared.
- `name = expression` assigns an expression's value. The old `name := expression` spelling is still accepted for compatibility.
- Expressions support integer literals, variables, parentheses, unary `+`/`-`, and binary `*`, `+`, `-`, with conventional precedence (`*` before `+`/`-`). Intermediate results wrap to the configured width.
- `input a` reads a signed decimal integer from standard input, skipping leading spaces, tabs, and newlines.
- `print a` prints a signed decimal value followed by a newline. The former `output(a)` syntax remains accepted.

### Conditions

Control-flow headers end in a colon. Indented blocks use tabs, one tab per level:

```text
if a == b:
	print a
else if a < b:
	print b
else:
	print a
```

Conditions support signed comparisons `==`, `!=`, `<`, `<=`, `>`, `>=`, and a bare expression (true when nonzero). Parentheses around conditions are optional.

### `while` loops

```text
new i = 0
while i < 3:
	print i
	i++
```

The condition is checked before every iteration. The body may be empty. `++`, `--`, `+=`, and `-=` are accepted as convenient assignment forms.

### `for` loops

The header uses C++-style semicolon-separated initialization, condition, and update, with a trailing colon and an indented body instead of braces:

```text
for (new i = 0; i < 5; i++):
	print i
```

The initialization and update parts may be assignments, and the update can use `i++`, `i--`, `i += expression`, or `i -= expression`. An empty condition means an infinite loop. If a loop variable was declared earlier, use `for (i = 0; i < n; i = i + 1):`.

### Comments and indentation

A comment line starts with `//` in column one. Use tabs rather than spaces for indentation. Variable names are global and may only be declared once; variables must be declared before they are referenced. A declaration inside a branch or loop still reserves global storage, while its initializer/clearing runs when the declaration statement executes.

## Architecture

- `prebf/ast.py` — AST nodes for expressions and statements.
- `prebf/parser.py` — tokenization, expression parsing, and indentation-based control-flow parsing.
- `prebf/semantics.py` — declaration and variable-reference validation.
- `prebf/bf.py` — Brainfuck emission, multi-limb arithmetic, signed comparisons, numeric input/output, and control-flow code generation.
- `prebf/compiler.py` — public `compile_source()` API.
- `prebf/cli.py` — command-line interface.
- `tests/` — parser/compiler regression tests and a small Brainfuck test runner.

New language constructs should be added to the AST, parser, semantic checker, and backend separately. This keeps future types, operators, and control structures manageable.

## Limitations

- Integer division, remainder, bitwise operators, functions, and user-defined types are not implemented yet.
- Brainfuck has no native arithmetic or comparisons, so generated programs can be large and slow, especially at higher logical bit widths and inside loops.
- `for` initializers use this language's `new name = expression` or `name = expression` forms; C++ type declarations such as `int i = 0` are not part of preBF.

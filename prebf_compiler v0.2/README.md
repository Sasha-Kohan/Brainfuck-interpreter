# preBF — modular compiler to Brainfuck

`preBF` reads `program.prebf`, parses an assembly-like language, validates variable declarations, and generates a plain Brainfuck program at `program.bf`. The compiler is written in Python and has no third-party dependencies.

## Quick start

Requires Python 3.10 or newer.

```bash
python main.py
```

By default this compiles `program.prebf` to `program.bf` with signed 8-bit integers. Choose any positive logical integer width with `--bits`:

```bash
python main.py --bits 16
python main.py --bits 32
python main.py --bits 64
python main.py --bits 12
```

The logical width is independent of the Brainfuck tape-cell width. The generated code targets ordinary wrapping 8-bit Brainfuck cells. Each integer is represented by little-endian 4-bit limbs, one limb per tape cell, so a `N`-bit variable occupies `ceil(N / 4)` cells. This supports widths that are not multiples of 8, such as 12 bits, while preserving signed two's-complement values.

Arithmetic wraps modulo `2**bits`. For example, a signed 16-bit number ranges from `-32768` through `32767`; adding 1 to `32767` produces `-32768`.

Input/output and arithmetic are implemented using generated Brainfuck loops. As expected for Brainfuck, wider numbers cost more time and produce larger programs.

## Language syntax

```text
// A comment is accepted only when // begins in column one.
new a
a := 67
a := b + c
a := b - c
input a
print a
if a == b
	print a
else
	print b
```

- `new a` declares and initializes variable `a`.
- `a := 67` assigns a signed integer constant.
- `a := b + c` and `a := b - c` compute from the original values of `b` and `c`; they do not modify the source variables.
- `input a` reads a decimal integer, skips leading spaces/tabs/newlines, and accepts an optional `+` or `-` sign.
- `print a` prints the signed decimal value followed by a newline.
- `if a == b` executes its indented block when the variables are equal; optional `else` executes otherwise. Blocks use tabs, one tab per indentation level. Empty blocks are allowed.

The previous spelling `output(a)` remains accepted as a backwards-compatible alias, but new examples should use `print a`.

Variables must be declared before use. Duplicate declarations, unknown variables, invalid commands, and space-based indentation produce an error with a source line number.

## Architecture

- `prebf/ast.py` — AST node definitions.
- `prebf/parser.py` — parsing and indentation validation.
- `prebf/semantics.py` — variable declaration/reference validation.
- `prebf/bf.py` — Brainfuck emitter, multi-cell signed arithmetic, numeric input/output, and conditional code generation.
- `prebf/compiler.py` — public `compile_source()` API.
- `prebf/cli.py` — command-line interface.
- `tests/` — parser/compiler tests and a small Brainfuck runner.

To add a future operation, add an AST node, parse it, validate it in the semantic pass, and implement its code generation in the backend. This keeps parsing, validation, and code generation separate.

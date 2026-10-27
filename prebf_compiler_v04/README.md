# preBF compiler v0.4

A modular compiler for an assembly-like, indentation-based language. It reads `program.prebf`, type-lowers and validates it, then generates plain Brainfuck in `program.bf`. Requires Python 3.10+ and has no third-party runtime dependencies.

## Quick start

```bash
python main.py
```

The defaults are `program.prebf` → `program.bf`, signed `int` width 8 bits, and maximum reserved capacity of 64 elements for arrays whose size is specified at runtime. Set integer width and dynamic-array capacity explicitly:

```bash
python main.py --bits 16
python main.py --bits 32 --max-array-size 128
python main.py --input examples/main.prebf --output main.bf --bits 16
```

Generated BF targets normal wrapping 8-bit cells. Integers use configurable signed two's-complement arithmetic spread across 4-bit limbs. `char` is stored as the low eight bits and printed as a character; `bool` is normalized to `0` or `1`.

## Primitive types and conversions

```text
new int a = 5
new bool same = a == 5
new char letter = 'R'
new int x = letter
new bool nonzero = x

new int a = 6, b = 7, c // declares three integers
```

Supported primitive types are `int`, `char`, and `bool`.

- `int` uses the signed width configured with `--bits`.
- `char` stores the low 8 bits of a value and `print` writes the corresponding character followed by a newline. A character literal must contain exactly one character; common escapes such as `\\n` and `\\t` are accepted.
- `bool` is always normalized to `0` or `1`. A nonzero numeric value converts to `true`; zero converts to `false`. Comparisons can initialize any type, e.g. `new bool t = a == b`.
- Numeric and character values automatically convert when assigned to another type: `char` to `int` uses its stored numeric value; assignments to `char` keep only the low 8 bits; assignments to `bool` normalize to `0`/`1`. As in C++, exact behavior at type-width boundaries depends on the selected integer width; `int` arithmetic wraps modulo `2**bits`.

Expressions retain v0.3 support: integer and character literals, variables, parentheses, unary `+`/`-`, and `*`, `+`, `-` operators with normal precedence. Comparisons support `==`, `!=`, `<`, `<=`, `>`, `>=` and are available in conditions and initializers/assignments.

## Pairs

A pair has two fields named `.first` and `.second`:

```text
new pair<int, char> p = {67, 'Y'}
p.first = 42
p.second = 'R'
print p.first
print p.second
```

Pair types may combine any two supported primitive types, e.g. `pair<bool, int>` or `pair<char, char>`. Uninitialized fields start at zero.

## Arrays

Fixed-size arrays reserve their full declared size:

```text
new int a[67]
a[5] = 42
new int b = a[5]
input a[6]
print b
print a.size()

new char str[10]
str[0] = 'H'
str[1] = 'i'
print str[0]
```

Arrays support primitive types and pairs. `a[index]` behaves like the corresponding scalar element for assignment, input, output, and expression evaluation. Indexing may use an expression such as `a[i + 1]`; the compiler expands dynamic indexing into runtime comparisons against each reserved slot. Out-of-range reads yield zero and writes/inputs/prints do nothing.

The array size is read-only through `a.size()`:

```text
new int n = 10
new int a[n]
print a.size()
```

The size expression may depend on a variable. Since Brainfuck has a static tape, dynamically sized arrays reserve a fixed maximum number of elements at compile time. `--max-array-size` sets this reserve (default 64). The runtime size is clamped to `0..max-array-size`; elements outside that runtime size cannot be accessed. Fixed-size arrays such as `new int a[67]` reserve exactly 67 entries and are not limited by `--max-array-size`.

Dynamic indexing inside `while`/`for` conditions and `else if` conditions is not supported in v0.4 because its selector must be reevaluated at the right control-flow point; move the indexed value to a temporary first. Dynamic indexing in a plain `if` condition and ordinary statements is supported.

## Control flow

Headers end with `:` and bodies use tabs:

```text
if a == b:
	print a
else if a < b:
	print b
else:
	print a

new int i = 0
while i < 3:
	print i
	i++

for (new int j = 0; j < 5; j++):
	print j
```

The for header contains C++-style initialization, condition, and update expressions separated by semicolons; braces are replaced by a colon and indentation.

## Input/output

```text
input a
print a
input letter
print letter
```

`input` on an `int` or `bool` reads a signed decimal number (booleans are normalized after reading). `input` on a `char` reads one non-whitespace byte. `print` on numeric values writes decimal notation plus a newline; `print` on a `char` writes the character plus a newline.

## Multiple declarations and comments

The type can be shared by comma-separated variables, each optionally initialized:

```text
new int a = 6, b = 7, c
new char first = 'A', second = 'B'
```

Line comments begin with `//`; trailing comments are also accepted outside character literals. Use tabs for block indentation, one tab per level.

## Architecture

- `prebf/ast.py` — core AST nodes, including character I/O and character conversion.
- `prebf/typesys.py` — v0.4 type checking/lowering, pairs, arrays, conversions, and multi-declarations.
- `prebf/parser.py` — expression parser and indentation-based control-flow parser.
- `prebf/semantics.py` — scalar-storage declaration/reference validation.
- `prebf/bf.py` — Brainfuck emitter, multi-limb arithmetic, comparisons, numeric/character I/O, and loops.
- `prebf/compiler.py` — public `compile_source()` API.
- `prebf/cli.py` — command-line options.
- `tests/` — automated tests and a small Brainfuck runner.

## Limitations

- No strings as a separate type, pair assignment as a whole, initializers for entire arrays, or variable-width integer types.
- Dynamic arrays reserve their maximum tape capacity at compile time; dynamic indexing expands to one comparison per element and can make generated BF large. Use `--max-array-size` appropriate to your program.
- Dynamic array indexing inside `while` and `for` conditions must be assigned to a temporary first.
- As with all Brainfuck programs, generated code can be slow for large arrays and wider integers.

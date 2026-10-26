"""Public compile API."""

from __future__ import annotations

from .bf import BrainfuckCompiler
from .parser import parse
from .semantics import validate


def compile_source(source: str, bits: int = 8) -> str:
    """Compile source using signed integers of the requested logical width.

    Values occupy ceil(bits / 4) ordinary 8-bit Brainfuck tape cells, with 4-bit limbs.
    """
    program = parse(source)
    variables = validate(program)
    return BrainfuckCompiler(bits=bits, variables=variables, program=program).compile()

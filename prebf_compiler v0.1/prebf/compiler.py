"""Public compile API."""

from __future__ import annotations

from .bf import BrainfuckCompiler
from .parser import parse
from .semantics import validate


def compile_source(source: str, bits: int = 8) -> str:
    program = parse(source)
    variables = validate(program)
    return BrainfuckCompiler(bits=bits, variables=variables, program=program).compile()

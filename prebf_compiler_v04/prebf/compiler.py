"""Public compile API."""

from __future__ import annotations

from .bf import BrainfuckCompiler
from .parser import parse
from .semantics import validate
from .typesys import TypeLowerer


def compile_source(source: str, bits: int = 8, max_array_size: int = 64) -> str:
    """Compile typed v0.4 source using signed integers of the requested width.

    Values occupy ceil(bits / 4) ordinary 8-bit Brainfuck tape cells, with 4-bit limbs.
    Dynamic-sized arrays reserve ``max_array_size`` elements in the generated tape.
    """
    lowerer = TypeLowerer(source, max_array_size=max_array_size)
    uses_char = any(
        symbol.type_spec == "char" or (isinstance(symbol.type_spec, tuple) and "char" in symbol.type_spec)
        for symbol in lowerer.symbols.values()
    )
    if bits < 8 and uses_char:
        raise ValueError("char requires --bits 8 or greater.")
    lowered_source = lowerer.lower()
    program = parse(lowered_source)
    variables = validate(program)
    return BrainfuckCompiler(bits=bits, variables=variables, program=program).compile()

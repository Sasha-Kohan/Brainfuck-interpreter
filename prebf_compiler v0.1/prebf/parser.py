"""Parser for the indentation-based preBF assembly-like language."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .ast import AssignBinary, AssignConst, If, Input, New, Output, Program, Statement
from .errors import PreBFError


@dataclass(frozen=True, slots=True)
class SourceLine:
    number: int
    indent: int
    text: str


_INT_RE = re.compile(r"[+-]?\d+\Z")
_ASSIGN_RE = re.compile(r"([^\s]+)\s*:=\s*(.*?)\s*\Z")
_BINARY_RE = re.compile(r"([^\s]+)\s*([+-])\s*([^\s]+)\Z")
_OUTPUT_RE = re.compile(r"output\s*\(\s*([^\s()]+)\s*\)\Z")
_IF_RE = re.compile(r"if\s+([^\s]+)\s*==\s*([^\s]+)\Z")


def _check_name(name: str, line: int) -> str:
    if not name.isidentifier():
        raise PreBFError(f"Недопустимое имя переменной {name!r}.", line)
    return name


def _source_lines(source: str) -> list[SourceLine]:
    result: list[SourceLine] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        # Comments are deliberately accepted only when // starts in column 1.
        if raw.startswith("//") or not raw.strip():
            continue

        if raw.startswith(" "):
            raise PreBFError("Для отступов используйте табуляцию, а не пробелы.", number)

        indent = len(raw) - len(raw.lstrip("\t"))
        text = raw[indent:]
        if text.startswith(" "):
            raise PreBFError("После табуляций не должно быть пробелов в начале команды.", number)
        result.append(SourceLine(number=number, indent=indent, text=text.rstrip()))
    return result


class Parser:
    def __init__(self, lines: list[SourceLine]) -> None:
        self.lines = lines
        self.pos = 0

    def parse(self) -> Program:
        statements = self._parse_block(indent=0)
        if self.pos != len(self.lines):
            line = self.lines[self.pos]
            raise PreBFError("Неожиданный отступ или лишняя команда.", line.number)
        return Program(statements)

    def _parse_block(self, indent: int) -> list[Statement]:
        statements: list[Statement] = []
        while self.pos < len(self.lines):
            source_line = self.lines[self.pos]
            if source_line.indent < indent:
                break
            if source_line.indent > indent:
                raise PreBFError("Неожиданный уровень отступа: используйте один таб на уровень.", source_line.number)

            text = source_line.text
            if text == "else":
                break

            if_match = _IF_RE.fullmatch(text)
            if if_match:
                left = _check_name(if_match.group(1), source_line.number)
                right = _check_name(if_match.group(2), source_line.number)
                self.pos += 1
                then_body = self._parse_block(indent + 1)
                else_body: list[Statement] | None = None
                if self.pos < len(self.lines):
                    maybe_else = self.lines[self.pos]
                    if maybe_else.indent == indent and maybe_else.text == "else":
                        self.pos += 1
                        else_body = self._parse_block(indent + 1)
                statements.append(If(left, right, then_body, else_body, source_line.number))
                continue

            if text == "else":
                raise PreBFError("else без соответствующего if.", source_line.number)

            statements.append(self._parse_simple(text, source_line.number))
            self.pos += 1

        return statements

    def _parse_simple(self, text: str, line: int) -> Statement:
        if text.startswith("new"):
            match = re.fullmatch(r"new\s+([^\s]+)", text)
            if match:
                return New(_check_name(match.group(1), line), line)

        if text.startswith("input"):
            match = re.fullmatch(r"input\s+([^\s]+)", text)
            if match:
                return Input(_check_name(match.group(1), line), line)

        output_match = _OUTPUT_RE.fullmatch(text)
        if output_match:
            return Output(_check_name(output_match.group(1), line), line)

        assign_match = _ASSIGN_RE.fullmatch(text)
        if assign_match:
            target = _check_name(assign_match.group(1), line)
            rhs = assign_match.group(2)
            if _INT_RE.fullmatch(rhs):
                return AssignConst(target, int(rhs), line)
            binary_match = _BINARY_RE.fullmatch(rhs)
            if binary_match:
                left = _check_name(binary_match.group(1), line)
                op = binary_match.group(2)
                right = _check_name(binary_match.group(3), line)
                return AssignBinary(target, left, op, right, line)
            raise PreBFError("Ожидалось целое число или выражение вида 'b + c' / 'b - c'.", line)

        raise PreBFError(
            "Неизвестная команда. Ожидается new, input, output(...), присваивание или if.",
            line,
        )


def parse(source: str) -> Program:
    """Parse source text into a program AST."""
    return Parser(_source_lines(source)).parse()

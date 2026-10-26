"""Abstract syntax tree nodes for the preBF language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class New:
    name: str
    line: int


@dataclass(frozen=True, slots=True)
class AssignConst:
    target: str
    value: int
    line: int


@dataclass(frozen=True, slots=True)
class AssignBinary:
    target: str
    left: str
    op: str
    right: str
    line: int


@dataclass(frozen=True, slots=True)
class Input:
    target: str
    line: int


@dataclass(frozen=True, slots=True)
class Output:
    name: str
    line: int


@dataclass(frozen=True, slots=True)
class If:
    left: str
    right: str
    then_body: list[Statement]
    else_body: list[Statement] | None
    line: int


Statement: TypeAlias = New | AssignConst | AssignBinary | Input | Output | If


@dataclass(frozen=True, slots=True)
class Program:
    statements: list[Statement]

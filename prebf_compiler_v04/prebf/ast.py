"""Abstract syntax tree for the preBF language."""

from __future__ import annotations
from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class Number:
    value: int


@dataclass(frozen=True, slots=True)
class Variable:
    name: str


@dataclass(frozen=True, slots=True)
class Unary:
    op: str
    operand: Expr


@dataclass(frozen=True, slots=True)
class Binary:
    op: str
    left: Expr
    right: Expr


Expr: TypeAlias = Number | Variable | Unary | Binary


@dataclass(frozen=True, slots=True)
class Condition:
    left: Expr
    op: str | None = None
    right: Expr | None = None


@dataclass(frozen=True, slots=True)
class New:
    name: str
    initializer: Expr | None
    line: int


@dataclass(frozen=True, slots=True)
class Assign:
    target: str
    value: Expr
    line: int


@dataclass(frozen=True, slots=True)
class Input:
    target: str
    line: int


@dataclass(frozen=True, slots=True)
class InputChar:
    target: str
    line: int


@dataclass(frozen=True, slots=True)
class Output:
    name: str
    line: int


@dataclass(frozen=True, slots=True)
class OutputChar:
    name: str
    line: int


@dataclass(frozen=True, slots=True)
class TruncateChar:
    target: str
    line: int


@dataclass(frozen=True, slots=True)
class IfBranch:
    condition: Condition | None  # None means the final `else` branch.
    body: list[Statement]


@dataclass(frozen=True, slots=True)
class If:
    branches: list[IfBranch]
    line: int


@dataclass(frozen=True, slots=True)
class While:
    condition: Condition
    body: list[Statement]
    line: int


@dataclass(frozen=True, slots=True)
class For:
    initializer: Statement | None
    condition: Condition | None  # None means an always-true condition.
    update: Statement | None
    body: list[Statement]
    line: int


Statement: TypeAlias = New | Assign | Input | InputChar | Output | OutputChar | TruncateChar | If | While | For


@dataclass(frozen=True, slots=True)
class Program:
    statements: list[Statement]

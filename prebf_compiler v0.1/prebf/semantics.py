"""Static checks for declarations and variable references."""

from __future__ import annotations

from .ast import AssignBinary, AssignConst, If, Input, New, Output, Program, Statement
from .errors import PreBFError


def validate(program: Program) -> list[str]:
    """Validate the program and return variable names in declaration order.

    Variables are global, statically allocated cells. A declaration may appear
    inside a conditional; its cell is zero-initialized at program start, and
    executing ``new`` clears it again.
    """
    declared: set[str] = set()
    ordered: list[str] = []

    def require(name: str, line: int) -> None:
        if name not in declared:
            raise PreBFError(f"Переменная {name!r} ещё не объявлена командой new.", line)

    def visit(statements: list[Statement]) -> None:
        for statement in statements:
            if isinstance(statement, New):
                if statement.name in declared:
                    raise PreBFError(f"Переменная {statement.name!r} объявлена повторно.", statement.line)
                declared.add(statement.name)
                ordered.append(statement.name)
            elif isinstance(statement, AssignConst):
                require(statement.target, statement.line)
            elif isinstance(statement, AssignBinary):
                require(statement.target, statement.line)
                require(statement.left, statement.line)
                require(statement.right, statement.line)
            elif isinstance(statement, Input):
                require(statement.target, statement.line)
            elif isinstance(statement, Output):
                require(statement.name, statement.line)
            elif isinstance(statement, If):
                require(statement.left, statement.line)
                require(statement.right, statement.line)
                visit(statement.then_body)
                if statement.else_body is not None:
                    visit(statement.else_body)
            else:  # pragma: no cover - defensive guard for future AST nodes
                raise TypeError(f"Неподдерживаемый узел AST: {type(statement).__name__}")

    visit(program.statements)
    return ordered

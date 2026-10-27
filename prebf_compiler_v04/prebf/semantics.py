"""Static checks for declarations and variable references."""
from __future__ import annotations

from .ast import (Assign, Binary, Expr, For, If, Input, InputChar, New, Number, Output, OutputChar, TruncateChar,
                  Program, Statement, Unary, Variable, While)
from .errors import PreBFError


def validate(program: Program) -> list[str]:
    """Validate variable references and return static storage order."""
    declared: set[str] = set()
    ordered: list[str] = []

    def require(name: str, line: int) -> None:
        if name not in declared:
            raise PreBFError(f"Переменная {name!r} ещё не объявлена командой new.", line)

    def expr_names(expr: Expr, line: int) -> None:
        if isinstance(expr, Variable):
            require(expr.name, line)
        elif isinstance(expr, Unary):
            expr_names(expr.operand, line)
        elif isinstance(expr, Binary):
            expr_names(expr.left, line)
            expr_names(expr.right, line)
        elif isinstance(expr, Number):
            return
        else:  # pragma: no cover
            raise TypeError(f"Unsupported expression node: {type(expr).__name__}")

    def condition_names(condition, line: int) -> None:
        expr_names(condition.left, line)
        if condition.right is not None:
            expr_names(condition.right, line)

    def visit_one(statement: Statement) -> None:
        if isinstance(statement, New):
            if statement.name in declared:
                raise PreBFError(f"Переменная {statement.name!r} объявлена повторно.", statement.line)
            declared.add(statement.name)
            ordered.append(statement.name)
            # The new variable is already declared when its initializer is checked.
            if statement.initializer is not None:
                expr_names(statement.initializer, statement.line)
        elif isinstance(statement, Assign):
            require(statement.target, statement.line)
            expr_names(statement.value, statement.line)
        elif isinstance(statement, (Input, InputChar, TruncateChar)):
            require(statement.target, statement.line)
        elif isinstance(statement, (Output, OutputChar)):
            require(statement.name, statement.line)
        elif isinstance(statement, If):
            for branch in statement.branches:
                if branch.condition is not None:
                    condition_names(branch.condition, statement.line)
                visit(branch.body)
        elif isinstance(statement, While):
            condition_names(statement.condition, statement.line)
            visit(statement.body)
        elif isinstance(statement, For):
            if statement.initializer is not None:
                visit_one(statement.initializer)
            if statement.condition is not None:
                condition_names(statement.condition, statement.line)
            if statement.update is not None:
                visit_one(statement.update)
            visit(statement.body)
        else:  # pragma: no cover
            raise TypeError(f"Unsupported AST node: {type(statement).__name__}")

    def visit(statements: list[Statement]) -> None:
        for statement in statements:
            visit_one(statement)

    visit(program.statements)
    return ordered

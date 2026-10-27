"""Parser for preBF expressions and colon/indentation-based control flow."""

from __future__ import annotations
import re
from dataclasses import dataclass

from .ast import (Assign, Binary, Condition, For, If, IfBranch, Input, InputChar, New,
                  Number, Output, OutputChar, TruncateChar, Program, Statement, Unary, Variable, While)
from .errors import PreBFError


@dataclass(frozen=True, slots=True)
class SourceLine:
    number: int
    indent: int
    text: str


_TOKEN_RE = re.compile(r"\s*(?:(\d+)|([A-Za-z_]\w*)|(==|!=|<=|>=|[()+\-*<>]))")
_COMPARISONS = {"==", "!=", "<", "<=", ">", ">="}


def _check_name(name: str, line: int) -> str:
    if not name.isidentifier():
        raise PreBFError(f"Недопустимое имя переменной {name!r}.", line)
    return name


def _tokens(text: str, line: int) -> list[str]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if not match:
            if text[pos:].strip() == "":
                break
            raise PreBFError(f"Недопустимый символ в выражении: {text[pos]!r}.", line)
        tokens.append(match.group(1) or match.group(2) or match.group(3))
        pos = match.end()
    return tokens


class ExpressionParser:
    def __init__(self, tokens: list[str], line: int) -> None:
        self.tokens = tokens
        self.line = line
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise PreBFError("Неожиданный конец выражения.", self.line)
        self.pos += 1
        return token

    def parse_expression(self, min_precedence: int = 0):
        token = self.take()
        if token in ("+", "-"):
            left = Unary(token, self.parse_expression(3))
        elif token == "(":
            left = self.parse_expression(0)
            if self.take() != ")":
                raise PreBFError("Ожидалась закрывающая скобка ')' .", self.line)
        elif token.isdigit():
            left = Number(int(token))
        elif token.isidentifier():
            left = Variable(_check_name(token, self.line))
        else:
            raise PreBFError(f"Неожиданный токен {token!r} в выражении.", self.line)

        precedence = {"+": 1, "-": 1, "*": 2}
        while self.peek() in precedence and precedence[self.peek()] >= min_precedence:
            op = self.take()
            right = self.parse_expression(precedence[op] + 1)
            left = Binary(op, left, right)
        return left

    def finish_expression(self):
        expr = self.parse_expression(0)
        if self.peek() is not None:
            raise PreBFError(f"Лишний токен {self.peek()!r} в выражении.", self.line)
        return expr


def _parse_expr(text: str, line: int):
    if not text.strip():
        raise PreBFError("Ожидалось выражение.", line)
    return ExpressionParser(_tokens(text, line), line).finish_expression()


def _strip_outer_parens(text: str) -> str:
    text = text.strip()
    if not (text.startswith("(") and text.endswith(")")):
        return text
    depth = 0
    for i, char in enumerate(text):
        if char == "(": depth += 1
        elif char == ")": depth -= 1
        if depth == 0 and i != len(text) - 1:
            return text
    return text[1:-1].strip()


def _parse_condition(text: str, line: int) -> Condition:
    text = _strip_outer_parens(text.strip())
    tokens = _tokens(text, line)
    depth = 0
    compare_at: int | None = None
    for i, token in enumerate(tokens):
        if token == "(": depth += 1
        elif token == ")": depth -= 1
        elif depth == 0 and token in _COMPARISONS:
            if compare_at is not None:
                raise PreBFError("Условие должно содержать только одно сравнение.", line)
            compare_at = i
    if compare_at is None:
        return Condition(ExpressionParser(tokens, line).finish_expression())
    op = tokens[compare_at]
    left = ExpressionParser(tokens[:compare_at], line).finish_expression()
    right = ExpressionParser(tokens[compare_at + 1:], line).finish_expression()
    return Condition(left, op, right)


def _source_lines(source: str) -> list[SourceLine]:
    result: list[SourceLine] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        if raw.startswith("//") or not raw.strip():
            continue
        if raw.startswith(" "):
            raise PreBFError("Для отступов используйте табуляцию, а не пробелы.", number)
        indent = len(raw) - len(raw.lstrip("\t"))
        text = raw[indent:].rstrip()
        if text.startswith(" "):
            raise PreBFError("После табуляций не должно быть пробелов в начале команды.", number)
        result.append(SourceLine(number, indent, text))
    return result


class Parser:
    def __init__(self, lines: list[SourceLine]) -> None:
        self.lines = lines
        self.pos = 0

    def parse(self) -> Program:
        statements = self._parse_block(0)
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
            if text == "else:" or text.startswith("else if "):
                break
            if text.startswith("if ") and text.endswith(":"):
                statements.append(self._parse_if(source_line, indent))
                continue
            if text.startswith("while ") and text.endswith(":"):
                statements.append(self._parse_while(source_line, indent))
                continue
            if text.startswith("for ") and text.endswith(":"):
                statements.append(self._parse_for(source_line, indent))
                continue
            if text in ("else", "else:") or text.startswith("else if "):
                raise PreBFError("else без соответствующего if.", source_line.number)
            statements.append(self._parse_simple(text, source_line.number))
            self.pos += 1
        return statements

    def _parse_if(self, first_line: SourceLine, indent: int) -> If:
        branches: list[IfBranch] = []
        header = first_line.text[:-1].strip()[3:].strip()
        branches.append(IfBranch(_parse_condition(header, first_line.number), []))
        self.pos += 1
        branches[-1] = IfBranch(branches[-1].condition, self._parse_block(indent + 1))
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            if line.indent != indent:
                break
            if line.text.startswith("else if ") and line.text.endswith(":"):
                condition_text = line.text[len("else if "):-1].strip()
                branches.append(IfBranch(_parse_condition(condition_text, line.number), []))
                self.pos += 1
                branches[-1] = IfBranch(branches[-1].condition, self._parse_block(indent + 1))
                continue
            if line.text == "else:":
                branches.append(IfBranch(None, []))
                self.pos += 1
                branches[-1] = IfBranch(None, self._parse_block(indent + 1))
            break
        return If(branches, first_line.number)

    def _parse_while(self, line: SourceLine, indent: int) -> While:
        header = line.text[len("while "):-1].strip()
        condition = _parse_condition(header, line.number)
        self.pos += 1
        body = self._parse_block(indent + 1)
        return While(condition, body, line.number)

    def _parse_for(self, line: SourceLine, indent: int) -> For:
        header = line.text[len("for "):-1].strip()
        if not (header.startswith("(") and header.endswith(")")):
            raise PreBFError("Ожидается формат for (init; condition; update):", line.number)
        parts = header[1:-1].split(";")
        if len(parts) != 3:
            raise PreBFError("В заголовке for должно быть две точки с запятой.", line.number)
        init_text, condition_text, update_text = (part.strip() for part in parts)
        initializer = self._parse_simple(init_text, line.number) if init_text else None
        condition = _parse_condition(condition_text, line.number) if condition_text else None
        update = self._parse_simple(update_text, line.number) if update_text else None
        self.pos += 1
        body = self._parse_block(indent + 1)
        return For(initializer, condition, update, body, line.number)

    def _parse_simple(self, text: str, line: int) -> Statement:
        if text.startswith("new"):
            match = re.fullmatch(r"new\s+([A-Za-z_]\w*)(?:\s*=\s*(.+))?", text)
            if match:
                init = _parse_expr(match.group(2), line) if match.group(2) is not None else None
                return New(_check_name(match.group(1), line), init, line)

        if text.startswith("inputchar"):
            match = re.fullmatch(r"inputchar\s+([A-Za-z_]\w*)", text)
            if match:
                return InputChar(_check_name(match.group(1), line), line)

        if text.startswith("input"):
            match = re.fullmatch(r"input\s+([A-Za-z_]\w*)", text)
            if match:
                return Input(_check_name(match.group(1), line), line)

        if text.startswith("printchar"):
            match = re.fullmatch(r"printchar\s+([A-Za-z_]\w*)", text)
            if match:
                return OutputChar(_check_name(match.group(1), line), line)

        truncate_match = re.fullmatch(r"truncatechar\s+([A-Za-z_]\w*)", text)
        if truncate_match:
            return TruncateChar(_check_name(truncate_match.group(1), line), line)

        print_match = re.fullmatch(r"print\s+([A-Za-z_]\w*)", text)
        if print_match:
            return Output(_check_name(print_match.group(1), line), line)
        legacy_output = re.fullmatch(r"output\s*\(\s*([A-Za-z_]\w*)\s*\)", text)
        if legacy_output:
            return Output(_check_name(legacy_output.group(1), line), line)

        postfix = re.fullmatch(r"([A-Za-z_]\w*)(\+\+|--)", text)
        if postfix:
            name = _check_name(postfix.group(1), line)
            op = "+" if postfix.group(2) == "++" else "-"
            return Assign(name, Binary(op, Variable(name), Number(1)), line)
        compound = re.fullmatch(r"([A-Za-z_]\w*)\s*(\+=|-=)\s*(.+)", text)
        if compound:
            name = _check_name(compound.group(1), line)
            op = "+" if compound.group(2) == "+=" else "-"
            return Assign(name, Binary(op, Variable(name), _parse_expr(compound.group(3), line)), line)

        assign_match = re.fullmatch(r"([A-Za-z_]\w*)\s*(=|:=)\s*(.+)", text)
        if assign_match:
            return Assign(_check_name(assign_match.group(1), line), _parse_expr(assign_match.group(3), line), line)
        raise PreBFError("Неизвестная команда. Ожидается new, input, print, присваивание, if, while или for.", line)


def parse(source: str) -> Program:
    return Parser(_source_lines(source)).parse()

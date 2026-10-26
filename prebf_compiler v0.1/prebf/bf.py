"""Brainfuck backend for the preBF compiler.

The backend uses one Brainfuck cell per number. Cells contain unsigned bit
patterns; arithmetic wraps modulo 2**bits, making signed integers two's
complement values. Decimal input/output is implemented in generated BF code.
"""

from __future__ import annotations

from typing import Callable

from .ast import AssignBinary, AssignConst, If, Input, New, Output, Program, Statement


class BFEmitter:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.pointer = 0

    def emit(self, code: str) -> None:
        self.parts.append(code)

    def move_to(self, cell: int) -> None:
        delta = cell - self.pointer
        if delta > 0:
            self.emit(">" * delta)
        elif delta < 0:
            self.emit("<" * (-delta))
        self.pointer = cell

    def op(self, cell: int, code: str) -> None:
        self.move_to(cell)
        self.emit(code)

    def clear(self, cell: int) -> None:
        self.op(cell, "[-]")

    def inc(self, cell: int) -> None:
        self.op(cell, "+")

    def dec(self, cell: int) -> None:
        self.op(cell, "-")

    def add_const(self, cell: int, value: int) -> None:
        if value > 0:
            self.op(cell, "+" * value)
        elif value < 0:
            self.op(cell, "-" * (-value))

    def set_const(self, cell: int, value: int, modulus: int) -> None:
        value %= modulus
        self.clear(cell)
        if value:
            self.op(cell, "+" * value)

    def read(self, cell: int) -> None:
        self.op(cell, ",")

    def write(self, cell: int) -> None:
        self.op(cell, ".")

    def while_cell(self, cell: int, body: Callable[[], None]) -> None:
        self.move_to(cell)
        self.emit("[")
        body()
        self.move_to(cell)
        self.emit("]")

    def if_any(self, cell: int, body: Callable[[], None]) -> None:
        """Run body once if cell is nonzero; clear the condition cell first."""
        self.move_to(cell)
        self.emit("[")
        self.emit("[-]")
        body()
        self.move_to(cell)
        self.emit("]")

    def finish(self) -> str:
        return "".join(self.parts)


class BrainfuckCompiler:
    # Scratch offsets are intentionally named rather than magic numbers.
    S = {
        "cmp_work": 0,
        "cmp_backup": 1,
        "eq_flag": 2,
        "char": 3,
        "digit": 4,
        "space": 5,
        "input_negative": 6,
        "minus": 7,
        "plus": 8,
        "has_sign": 9,
        "digit_valid": 10,
        "multiply_work": 11,
        "out_magnitude": 12,
        "sign": 13,
        "sign_print": 14,
        "sign_counter": 15,
        "sign_work": 16,
        "zero_copy": 17,
        "zero_flag": 18,
        "nonzero_copy": 19,
        "quotient": 20,
        "remainder": 21,
        "division_work": 22,
        "out_char": 23,
        "started": 24,
        "digit_nonzero": 25,
        "should_print": 26,
        "branch_copy": 27,
        "decimal_0": 28,
        "decimal_1": 29,
        "decimal_2": 30,
        "decimal_3": 31,
        "decimal_4": 32,
    }
    SCRATCH_COUNT = max(S.values()) + 1

    def __init__(self, bits: int, variables: list[str], program: Program) -> None:
        if bits not in (8, 16):
            raise ValueError("Поддерживаются разрядности 8 и 16 бит.")
        self.bits = bits
        self.modulus = 1 << bits
        self.sign_threshold = 1 << (bits - 1)
        self.decimal_digits = len(str(self.sign_threshold))
        self.variables = variables
        self.address = {name: i for i, name in enumerate(variables)}
        self.base = len(variables)
        self.emitter = BFEmitter()
        self.program = program
        self.if_addresses: dict[int, tuple[int, int]] = {}
        self._allocate_if_cells(program.statements)
        self.total_cells = self.base + self.SCRATCH_COUNT + 2 * len(self.if_addresses)

    def s(self, name: str) -> int:
        return self.base + self.S[name]

    def _allocate_if_cells(self, statements: list[Statement]) -> None:
        cursor = self.base + self.SCRATCH_COUNT

        def visit(items: list[Statement]) -> None:
            nonlocal cursor
            for item in items:
                if isinstance(item, If):
                    self.if_addresses[id(item)] = (cursor, cursor + 1)
                    cursor += 2
                    visit(item.then_body)
                    if item.else_body is not None:
                        visit(item.else_body)

        visit(statements)

    def compile(self) -> str:
        # Brainfuck tapes normally start with zeroes, but explicit initialization
        # makes the generated program independent of previous tape contents.
        for cell in range(self.total_cells):
            self.emitter.clear(cell)
        self._compile_block(self.program.statements)
        return self.emitter.finish()

    def _copy(self, src: int, dst: int, temp: int) -> None:
        if len({src, dst, temp}) != 3:
            raise ValueError("copy requires three distinct cells")
        e = self.emitter
        e.clear(dst)
        e.clear(temp)

        def take_one() -> None:
            e.dec(src)
            e.inc(dst)
            e.inc(temp)

        e.while_cell(src, take_one)

        def restore_one() -> None:
            e.dec(temp)
            e.inc(src)

        e.while_cell(temp, restore_one)

    def _move(self, src: int, dst: int) -> None:
        if src == dst:
            return
        e = self.emitter
        e.clear(dst)

        def transfer_one() -> None:
            e.dec(src)
            e.inc(dst)

        e.while_cell(src, transfer_one)

    def _add_cell(self, src: int, dst: int, temp: int) -> None:
        if len({src, dst, temp}) != 3:
            raise ValueError("add_cell requires three distinct cells")
        e = self.emitter
        e.clear(temp)

        def add_one() -> None:
            e.dec(src)
            e.inc(dst)
            e.inc(temp)

        e.while_cell(src, add_one)

        def restore_one() -> None:
            e.dec(temp)
            e.inc(src)

        e.while_cell(temp, restore_one)

    def _sub_cell(self, src: int, dst: int, temp: int) -> None:
        if len({src, dst, temp}) != 3:
            raise ValueError("sub_cell requires three distinct cells")
        e = self.emitter
        e.clear(temp)

        def sub_one() -> None:
            e.dec(src)
            e.dec(dst)
            e.inc(temp)

        e.while_cell(src, sub_one)

        def restore_one() -> None:
            e.dec(temp)
            e.inc(src)

        e.while_cell(temp, restore_one)

    def _zero_test_destructive(self, cell: int, flag: int) -> None:
        e = self.emitter
        e.set_const(flag, 1, self.modulus)
        e.if_any(cell, lambda: e.clear(flag))

    def _eq_const(self, src: int, value: int, flag: int) -> None:
        work = self.s("cmp_work")
        backup = self.s("cmp_backup")
        self._copy(src, work, backup)
        self.emitter.add_const(work, -value)
        self._zero_test_destructive(work, flag)

    def _eq_cells(self, left: int, right: int, flag: int) -> None:
        work = self.s("cmp_work")
        backup = self.s("cmp_backup")
        self._copy(left, work, backup)
        self._sub_cell(right, work, backup)
        self._zero_test_destructive(work, flag)

    def _nonzero(self, src: int, flag: int) -> None:
        work = self.s("nonzero_copy")
        self._copy(src, work, self.s("cmp_backup"))
        self.emitter.clear(flag)
        self.emitter.if_any(work, lambda: self.emitter.set_const(flag, 1, self.modulus))

    def _compile_block(self, statements: list[Statement]) -> None:
        for statement in statements:
            if isinstance(statement, New):
                self.emitter.clear(self.address[statement.name])
            elif isinstance(statement, AssignConst):
                raw = statement.value % self.modulus
                self.emitter.set_const(self.address[statement.target], raw, self.modulus)
            elif isinstance(statement, AssignBinary):
                result = self.s("multiply_work")
                temp = self.s("cmp_backup")
                self.emitter.clear(result)
                self._copy(self.address[statement.left], result, temp)
                if statement.op == "+":
                    self._add_cell(self.address[statement.right], result, temp)
                else:
                    self._sub_cell(self.address[statement.right], result, temp)
                self._move(result, self.address[statement.target])
            elif isinstance(statement, Input):
                self._compile_input(self.address[statement.target])
            elif isinstance(statement, Output):
                self._compile_output(self.address[statement.name])
            elif isinstance(statement, If):
                self._compile_if(statement)
            else:  # pragma: no cover - defensive guard for future AST nodes
                raise TypeError(f"Неподдерживаемый узел AST: {type(statement).__name__}")

    def _compile_if(self, statement: If) -> None:
        then_flag, else_flag = self.if_addresses[id(statement)]
        self._eq_cells(self.address[statement.left], self.address[statement.right], then_flag)

        if statement.else_body is not None:
            self.emitter.set_const(else_flag, 1, self.modulus)
            branch_copy = self.s("branch_copy")
            self._copy(then_flag, branch_copy, self.s("cmp_backup"))
            self.emitter.if_any(branch_copy, lambda: self.emitter.clear(else_flag))

        self.emitter.if_any(then_flag, lambda: self._compile_block(statement.then_body))
        if statement.else_body is not None:
            self.emitter.if_any(else_flag, lambda: self._compile_block(statement.else_body or []))

    def _compile_input(self, target: int) -> None:
        e = self.emitter
        char = self.s("char")
        digit = self.s("digit")
        space = self.s("space")
        neg_input = self.s("input_negative")
        minus = self.s("minus")
        plus = self.s("plus")
        has_sign = self.s("has_sign")
        valid = self.s("digit_valid")
        eq = self.s("eq_flag")

        e.clear(target)
        e.read(char)

        def calculate_space() -> None:
            e.clear(space)
            for code in (9, 10, 13, 32):
                self._eq_const(char, code, eq)
                e.if_any(eq, lambda: e.set_const(space, 1, self.modulus))

        calculate_space()

        def skip_one_space() -> None:
            e.clear(space)
            e.read(char)
            calculate_space()

        e.while_cell(space, skip_one_space)

        self._eq_const(char, ord("-"), neg_input)
        self._eq_const(char, ord("-"), minus)
        self._eq_const(char, ord("+"), plus)
        e.clear(has_sign)
        e.if_any(minus, lambda: e.set_const(has_sign, 1, self.modulus))
        e.if_any(plus, lambda: e.set_const(has_sign, 1, self.modulus))
        e.if_any(has_sign, lambda: e.read(char))

        def calculate_digit() -> None:
            e.clear(valid)
            e.clear(digit)
            for value in range(10):
                self._eq_const(char, ord("0") + value, eq)

                def set_digit(value: int = value) -> None:
                    e.set_const(digit, value, self.modulus)
                    e.set_const(valid, 1, self.modulus)

                e.if_any(eq, set_digit)

        calculate_digit()

        def parse_one_digit() -> None:
            e.clear(valid)
            multiply_work = self.s("multiply_work")
            e.clear(multiply_work)
            self._copy(target, multiply_work, self.s("cmp_backup"))
            e.clear(target)

            def add_ten() -> None:
                e.dec(multiply_work)
                e.add_const(target, 10)

            e.while_cell(multiply_work, add_ten)

            def transfer_digit() -> None:
                e.dec(digit)
                e.inc(target)

            e.while_cell(digit, transfer_digit)
            e.read(char)
            calculate_digit()

        e.while_cell(valid, parse_one_digit)

        def make_negative() -> None:
            work = self.s("multiply_work")
            self._move(target, work)

            def subtract_one() -> None:
                e.dec(work)
                e.dec(target)

            e.while_cell(work, subtract_one)

        e.if_any(neg_input, make_negative)

    def _compile_output(self, source: int) -> None:
        e = self.emitter
        cmp_backup = self.s("cmp_backup")
        sign = self.s("sign")
        sign_print = self.s("sign_print")
        counter = self.s("sign_counter")
        work = self.s("sign_work")
        zero_copy = self.s("zero_copy")
        zero_flag = self.s("zero_flag")
        nonzero_copy = self.s("nonzero_copy")

        # A portable BF cell has no signed comparison instruction. Determine
        # whether raw >= 2**(bits-1) by counting down a copy to the sign boundary.
        self._copy(source, work, cmp_backup)
        e.set_const(sign, 1, self.modulus)
        e.set_const(counter, self.sign_threshold, self.modulus)

        def sign_compare_step() -> None:
            self._copy(work, zero_copy, cmp_backup)
            self._zero_test_destructive(zero_copy, zero_flag)
            e.if_any(zero_flag, lambda: e.clear(sign))
            self._copy(work, nonzero_copy, cmp_backup)
            e.if_any(nonzero_copy, lambda: e.dec(work))
            e.dec(counter)

        e.while_cell(counter, sign_compare_step)

        out_magnitude = self.s("out_magnitude")
        self._copy(source, out_magnitude, cmp_backup)
        self._copy(sign, sign_print, cmp_backup)

        def negate_magnitude() -> None:
            neg_work = self.s("multiply_work")
            self._move(out_magnitude, neg_work)

            def subtract_one() -> None:
                e.dec(neg_work)
                e.dec(out_magnitude)

            e.while_cell(neg_work, subtract_one)

        e.if_any(sign, negate_magnitude)

        def print_minus() -> None:
            out_char = self.s("out_char")
            e.set_const(out_char, ord("-"), self.modulus)
            e.write(out_char)
            e.clear(out_char)

        e.if_any(sign_print, print_minus)

        digit_cells = [self.s(f"decimal_{i}") for i in range(self.decimal_digits)]
        quotient = self.s("quotient")
        remainder = self.s("remainder")
        division_work = self.s("division_work")
        eq = self.s("eq_flag")

        for digit_cell in digit_cells:
            e.clear(digit_cell)
            e.clear(quotient)
            e.clear(remainder)
            self._copy(out_magnitude, division_work, cmp_backup)

            def division_step() -> None:
                e.dec(division_work)
                e.inc(remainder)
                self._eq_const(remainder, 10, eq)

                def carry_digit() -> None:
                    e.clear(remainder)
                    e.inc(quotient)

                e.if_any(eq, carry_digit)

            e.while_cell(division_work, division_step)
            self._move(remainder, digit_cell)
            self._move(quotient, out_magnitude)

        started = self.s("started")
        digit_nonzero = self.s("digit_nonzero")
        should_print = self.s("should_print")
        out_char = self.s("out_char")
        e.clear(started)

        for index in reversed(range(len(digit_cells))):
            digit_cell = digit_cells[index]
            self._nonzero(digit_cell, digit_nonzero)
            self._copy(started, should_print, cmp_backup)
            e.if_any(digit_nonzero, lambda: e.set_const(should_print, 1, self.modulus))
            if index == 0:
                e.set_const(should_print, 1, self.modulus)

            def print_digit(digit_cell: int = digit_cell) -> None:
                e.set_const(started, 1, self.modulus)
                self._copy(digit_cell, out_char, cmp_backup)
                e.add_const(out_char, ord("0"))
                e.write(out_char)
                e.clear(out_char)

            e.if_any(should_print, print_digit)

        # Each output statement ends with a newline to keep adjacent values legible.
        e.set_const(out_char, 10, self.modulus)
        e.write(out_char)
        e.clear(out_char)

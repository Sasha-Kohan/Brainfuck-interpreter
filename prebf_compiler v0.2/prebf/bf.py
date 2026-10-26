"""Brainfuck backend for preBF.

Logical integers use little-endian 4-bit limbs stored in ordinary 8-bit
Brainfuck cells. The requested width may be any positive number of bits; unused
bits in the highest limb are masked after arithmetic and input. Arithmetic wraps
modulo 2**bits and signed values use two's-complement representation.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator, Sequence

from .ast import AssignBinary, AssignConst, If, Input, New, Output, Program, Statement

TAPE_CELL_BITS = 8
TAPE_CELL_MODULUS = 1 << TAPE_CELL_BITS
LIMB_BITS = 4
LIMB_BASE = 1 << LIMB_BITS
LIMB_MASK = LIMB_BASE - 1


class BFEmitter:
    """Small, pointer-aware emitter for standard 8-bit-cell Brainfuck."""

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
        value %= TAPE_CELL_MODULUS
        if value == 0:
            return
        if value <= TAPE_CELL_MODULUS // 2:
            self.op(cell, "+" * value)
        else:
            self.op(cell, "-" * (TAPE_CELL_MODULUS - value))

    def set_const(self, cell: int, value: int) -> None:
        value %= TAPE_CELL_MODULUS
        self.clear(cell)
        self.add_const(cell, value)

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
        """Run body once if cell is nonzero, consuming the condition cell."""
        self.move_to(cell)
        self.emit("[")
        self.emit("[-]")
        body()
        self.move_to(cell)
        self.emit("]")

    def finish(self) -> str:
        return "".join(self.parts)


class BrainfuckCompiler:
    """Compile preBF AST to Brainfuck operating on 8-bit tape cells."""

    def __init__(self, bits: int, variables: list[str], program: Program) -> None:
        if bits < 1:
            raise ValueError("The number width must be a positive integer.")
        self.bits = bits
        self.limb_width = (bits + LIMB_BITS - 1) // LIMB_BITS
        self.top_bits = bits % LIMB_BITS or LIMB_BITS
        self.top_mask = (1 << self.top_bits) - 1
        self.sign_bit = 1 << ((bits - 1) % LIMB_BITS)
        self.decimal_digits = len(str(1 << (bits - 1)))
        self.variables = variables
        self.address: dict[str, list[int]] = {
            name: [i * self.limb_width + j for j in range(self.limb_width)]
            for i, name in enumerate(variables)
        }
        self.variable_cells = len(variables) * self.limb_width
        self._scratch_cursor = self.variable_cells
        self.emitter = BFEmitter()
        self.program = program

    @contextmanager
    def _scratch_scope(self) -> Iterator[None]:
        """Reuse scratch tape cells after a generated code fragment completes.

        Nested helpers get cells above their caller's live cells. Generated BF
        code is static, so scratch storage can be reused by later fragments.
        """
        mark = self._scratch_cursor
        try:
            yield
        finally:
            self._scratch_cursor = mark

    def _alloc(self) -> int:
        cell = self._scratch_cursor
        self._scratch_cursor += 1
        return cell

    def _alloc_vector(self) -> list[int]:
        return [self._alloc() for _ in range(self.limb_width)]

    def compile(self) -> str:
        # Explicitly initialize variables. All scratch cells are initialized by
        # the helper that first uses them; standard BF tapes start at zero.
        for cell in range(self.variable_cells):
            self.emitter.clear(cell)
        self._compile_block(self.program.statements)
        return self.emitter.finish()

    def _copy(self, src: int, dst: int) -> None:
        if src == dst:
            return
        with self._scratch_scope():
            e = self.emitter
            temp = self._alloc()
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

    def _copy_vector(self, src: Sequence[int], dst: Sequence[int]) -> None:
        for src_byte, dst_byte in zip(src, dst):
            self._copy(src_byte, dst_byte)

    def _move_vector(self, src: Sequence[int], dst: Sequence[int]) -> None:
        for src_byte, dst_byte in zip(src, dst):
            self._move(src_byte, dst_byte)

    def _is_zero(self, src: int, flag: int) -> None:
        with self._scratch_scope():
            e = self.emitter
            copy = self._alloc()
            self._copy(src, copy)
            e.set_const(flag, 1)
            e.if_any(copy, lambda: e.clear(flag))

    def _nonzero(self, src: int, flag: int) -> None:
        with self._scratch_scope():
            zero_flag = self._alloc()
            self._is_zero(src, zero_flag)
            self.emitter.set_const(flag, 1)
            self.emitter.if_any(zero_flag, lambda: self.emitter.clear(flag))

    def _eq_const(self, src: int, value: int, flag: int) -> None:
        with self._scratch_scope():
            work = self._alloc()
            self._copy(src, work)
            self.emitter.add_const(work, -value)
            self._is_zero(work, flag)

    def _add_limb(self, src: int, dst: int, carry_in: int, carry_out: int) -> None:
        """Add base-16 limbs, preserving src and propagating a carry bit."""
        with self._scratch_scope():
            e = self.emitter
            counter = self._alloc()
            overflow = self._alloc()
            e.clear(carry_out)
            self._copy(src, counter)

            def add_one() -> None:
                e.dec(counter)
                e.inc(dst)
                self._eq_const(dst, LIMB_BASE, overflow)

                def wrap_limb() -> None:
                    e.clear(dst)
                    e.set_const(carry_out, 1)

                e.if_any(overflow, wrap_limb)

            e.while_cell(counter, add_one)

            def add_carry() -> None:
                e.inc(dst)
                self._eq_const(dst, LIMB_BASE, overflow)

                def wrap_limb() -> None:
                    e.clear(dst)
                    e.set_const(carry_out, 1)

                e.if_any(overflow, wrap_limb)

            e.if_any(carry_in, add_carry)

    def _propagate_carry(self, carry_in: int, dst: int, carry_out: int) -> None:
        with self._scratch_scope():
            e = self.emitter
            overflow = self._alloc()
            e.clear(carry_out)

            def increment_once() -> None:
                e.inc(dst)
                self._eq_const(dst, LIMB_BASE, overflow)

                def wrap_limb() -> None:
                    e.clear(dst)
                    e.set_const(carry_out, 1)

                e.if_any(overflow, wrap_limb)

            e.if_any(carry_in, increment_once)

    def _sub_limb(self, src: int, dst: int, borrow_in: int, borrow_out: int) -> None:
        """Subtract base-16 limbs, preserving src and propagating a borrow."""
        with self._scratch_scope():
            e = self.emitter
            counter = self._alloc()
            zero_flag = self._alloc()
            zero_copy = self._alloc()
            e.clear(borrow_out)
            self._copy(src, counter)

            def subtract_one() -> None:
                self._is_zero(dst, zero_flag)
                self._copy(zero_flag, zero_copy)

                def wrap_limb() -> None:
                    e.set_const(dst, LIMB_MASK)
                    e.set_const(borrow_out, 1)

                e.if_any(zero_copy, wrap_limb)
                self._if_flag_zero(zero_flag, lambda: e.dec(dst))
                e.dec(counter)

            e.while_cell(counter, subtract_one)

            def subtract_borrow() -> None:
                self._is_zero(dst, zero_flag)
                self._copy(zero_flag, zero_copy)

                def wrap_limb() -> None:
                    e.set_const(dst, LIMB_MASK)
                    e.set_const(borrow_out, 1)

                e.if_any(zero_copy, wrap_limb)
                self._if_flag_zero(zero_flag, lambda: e.dec(dst))

            e.if_any(borrow_in, subtract_borrow)

    def _add_vectors(self, src: Sequence[int], dst: Sequence[int]) -> None:
        """Add little-endian vectors, propagating carries; preserve src."""
        with self._scratch_scope():
            e = self.emitter
            carry_a = self._alloc()
            carry_b = self._alloc()
            e.clear(carry_a)
            e.clear(carry_b)
            for src_byte, dst_byte in zip(src, dst):
                self._add_limb(src_byte, dst_byte, carry_a, carry_b)
                carry_a, carry_b = carry_b, carry_a

    def _sub_vectors(self, src: Sequence[int], dst: Sequence[int]) -> None:
        """Subtract little-endian src vector from dst vector."""
        with self._scratch_scope():
            e = self.emitter
            borrow_a = self._alloc()
            borrow_b = self._alloc()
            e.clear(borrow_a)
            e.clear(borrow_b)
            for src_byte, dst_byte in zip(src, dst):
                self._sub_limb(src_byte, dst_byte, borrow_a, borrow_b)
                borrow_a, borrow_b = borrow_b, borrow_a

    def _add_one_vector(self, vector: Sequence[int]) -> None:
        with self._scratch_scope():
            if not vector:
                return
            e = self.emitter
            carry_a = self._alloc()
            carry_b = self._alloc()
            e.clear(carry_a)
            e.set_const(carry_b, 1)
            for byte in vector:
                self._propagate_carry(carry_b, byte, carry_a)
                carry_a, carry_b = carry_b, carry_a

    def _mask_top(self, vector: Sequence[int]) -> None:
        if self.top_mask == LIMB_MASK:
            return
        with self._scratch_scope():
            e = self.emitter
            top = vector[-1]
            work = self._alloc()
            remainder = self._alloc()
            flag = self._alloc()
            self._copy(top, work)
            e.clear(remainder)

            def count_one() -> None:
                e.dec(work)
                e.inc(remainder)
                self._eq_const(remainder, self.top_mask + 1, flag)
                e.if_any(flag, lambda: e.clear(remainder))

            e.while_cell(work, count_one)
            e.clear(top)
            self._move(remainder, top)

    def _negate_vector(self, src: Sequence[int], dst: Sequence[int]) -> None:
        """Write abs(two's-complement negative src) to dst, modulo 2**bits."""
        with self._scratch_scope():
            e = self.emitter
            for index, (src_byte, dst_byte) in enumerate(zip(src, dst)):
                max_byte = self.top_mask if index == self.limb_width - 1 else LIMB_MASK
                e.set_const(dst_byte, max_byte)
                borrow_in = self._alloc()
                borrow_out = self._alloc()
                e.clear(borrow_in)
                self._sub_limb(src_byte, dst_byte, borrow_in, borrow_out)
            self._add_one_vector(dst)
            self._mask_top(dst)

    def _eq_vectors(self, left: Sequence[int], right: Sequence[int], flag: int) -> None:
        with self._scratch_scope():
            e = self.emitter
            work = self._alloc_vector()
            byte_zero = self._alloc()
            still_equal = self._alloc()
            self._copy_vector(left, work)
            self._sub_vectors(right, work)
            e.set_const(flag, 1)
            for byte in work:
                # If this byte is not zero, the whole vectors are unequal.
                self._nonzero(byte, still_equal)
                e.if_any(still_equal, lambda: e.clear(flag))

    def _if_flag_zero(self, flag: int, body: Callable[[], None]) -> None:
        with self._scratch_scope():
            inverse = self._alloc()
            self.emitter.set_const(inverse, 1)
            self.emitter.if_any(flag, lambda: self.emitter.clear(inverse))
            self.emitter.if_any(inverse, body)

    def _compile_block(self, statements: list[Statement]) -> None:
        for statement in statements:
            with self._scratch_scope():
                if isinstance(statement, New):
                    for cell in self.address[statement.name]:
                        self.emitter.clear(cell)
                elif isinstance(statement, AssignConst):
                    value = statement.value % (1 << self.bits)
                    vector = self.address[statement.target]
                    for index, cell in enumerate(vector):
                        self.emitter.set_const(cell, (value >> (LIMB_BITS * index)) & LIMB_MASK)
                    self._mask_top(vector)
                elif isinstance(statement, AssignBinary):
                    left = self.address[statement.left]
                    right = self.address[statement.right]
                    result = self._alloc_vector()
                    self._copy_vector(left, result)
                    if statement.op == "+":
                        self._add_vectors(right, result)
                    else:
                        self._sub_vectors(right, result)
                    self._mask_top(result)
                    self._move_vector(result, self.address[statement.target])
                elif isinstance(statement, Input):
                    self._compile_input(self.address[statement.target])
                elif isinstance(statement, Output):
                    self._compile_output(self.address[statement.name])
                elif isinstance(statement, If):
                    self._compile_if(statement)
                else:  # pragma: no cover - defensive guard for future AST nodes
                    raise TypeError(f"Unsupported AST node: {type(statement).__name__}")

    def _compile_if(self, statement: If) -> None:
        e = self.emitter
        then_flag = self._alloc()
        else_flag = self._alloc() if statement.else_body is not None else None
        self._eq_vectors(self.address[statement.left], self.address[statement.right], then_flag)

        if else_flag is not None:
            self._is_zero(then_flag, else_flag)
        e.if_any(then_flag, lambda: self._compile_block(statement.then_body))
        if else_flag is not None:
            e.if_any(else_flag, lambda: self._compile_block(statement.else_body or []))

    def _compile_input(self, target: list[int]) -> None:
        with self._scratch_scope():
            e = self.emitter
            char = self._alloc()
            digit = self._alloc()
            space = self._alloc()
            negative = self._alloc()
            minus = self._alloc()
            plus = self._alloc()
            has_sign = self._alloc()
            valid = self._alloc()
            eq = self._alloc()
            old = self._alloc_vector()

            for cell in target:
                e.clear(cell)
            e.read(char)

            def calculate_space() -> None:
                e.clear(space)
                for code in (9, 10, 13, 32):
                    self._eq_const(char, code, eq)
                    e.if_any(eq, lambda: e.set_const(space, 1))

            calculate_space()

            def skip_one_space() -> None:
                e.clear(space)
                e.read(char)
                calculate_space()

            e.while_cell(space, skip_one_space)

            self._eq_const(char, ord("-"), negative)
            self._eq_const(char, ord("-"), minus)
            self._eq_const(char, ord("+"), plus)
            e.clear(has_sign)
            e.if_any(minus, lambda: e.set_const(has_sign, 1))
            e.if_any(plus, lambda: e.set_const(has_sign, 1))
            e.if_any(has_sign, lambda: e.read(char))

            def calculate_digit() -> None:
                e.clear(valid)
                e.clear(digit)
                for number in range(10):
                    self._eq_const(char, ord("0") + number, eq)

                    def set_digit(number: int = number) -> None:
                        e.set_const(digit, number)
                        e.set_const(valid, 1)

                    e.if_any(eq, set_digit)

            calculate_digit()

            def parse_one_digit() -> None:
                e.clear(valid)
                self._copy_vector(target, old)
                for cell in target:
                    e.clear(cell)
                # Decimal accumulation: target := old * 10 + digit. The source
                # snapshot allows the same compact vector-add helper to be used
                # for each of the ten additions.
                for _ in range(10):
                    self._add_vectors(old, target)
                self._mask_top(target)

                carry_a = self._alloc()
                carry_b = self._alloc()
                e.clear(carry_a)
                self._add_limb(digit, target[0], carry_a, carry_b)
                carry_in, carry_out = carry_b, carry_a
                for cell in target[1:]:
                    self._propagate_carry(carry_in, cell, carry_out)
                    carry_in, carry_out = carry_out, carry_in
                self._mask_top(target)
                e.read(char)
                calculate_digit()

            e.while_cell(valid, parse_one_digit)

            def make_negative() -> None:
                negated = self._alloc_vector()
                self._negate_vector(target, negated)
                self._move_vector(negated, target)

            e.if_any(negative, make_negative)
            self._mask_top(target)

    def _divide_vector_by_10(self, value: Sequence[int], digit_cell: int) -> None:
        """Divide a base-16 limb vector by ten, leaving remainder in digit_cell.

        For each limb, n = previous_remainder*16 + limb. Because
        16 = 10 + 6, calculate t = limb + 6*previous_remainder, then
        quotient_limb = previous_remainder + floor(t/10). Here t is at most
        69, so decimal conversion has a small, width-independent inner loop.
        """
        with self._scratch_scope():
            e = self.emitter
            remainder = self._alloc()
            old_remainder = self._alloc()
            work = self._alloc()
            quotient_limb = self._alloc()
            rem_count = self._alloc()
            counter = self._alloc()
            eq_ten = self._alloc()
            e.clear(remainder)

            for value_limb in reversed(value):
                self._copy(remainder, old_remainder)
                self._copy(value_limb, work)
                self._copy(old_remainder, counter)

                def add_six() -> None:
                    e.dec(counter)
                    e.add_const(work, 6)

                e.while_cell(counter, add_six)
                e.clear(quotient_limb)
                e.clear(rem_count)

                def divide_work() -> None:
                    e.dec(work)
                    e.inc(rem_count)
                    self._eq_const(rem_count, 10, eq_ten)

                    def carry_quotient() -> None:
                        e.clear(rem_count)
                        e.inc(quotient_limb)

                    e.if_any(eq_ten, carry_quotient)

                e.while_cell(work, divide_work)

                # quotient_limb = floor(t/10) + old_remainder, at most 15.
                self._copy(old_remainder, counter)

                def add_previous_remainder() -> None:
                    e.dec(counter)
                    e.inc(quotient_limb)

                e.while_cell(counter, add_previous_remainder)
                self._move(quotient_limb, value_limb)
                self._move(rem_count, remainder)

            self._move(remainder, digit_cell)

    def _compile_output(self, source: list[int]) -> None:
        with self._scratch_scope():
            e = self.emitter
            sign = self._alloc()
            sign_print = self._alloc()
            sign_work = self._alloc()
            sign_counter = self._alloc()
            magnitude = self._alloc_vector()

            self._copy_vector(source, magnitude)
            # The sign is the highest logical bit in the top byte, not the
            # sign bit of an arbitrarily wide BF tape cell.
            self._copy(source[-1], sign_work)
            e.set_const(sign, 1)
            e.set_const(sign_counter, self.sign_bit)

            def sign_compare_step() -> None:
                zero = self._alloc()
                self._is_zero(sign_work, zero)
                e.if_any(zero, lambda: e.clear(sign))
                nonzero = self._alloc()
                self._nonzero(sign_work, nonzero)
                e.if_any(nonzero, lambda: e.dec(sign_work))
                e.dec(sign_counter)

            e.while_cell(sign_counter, sign_compare_step)
            self._copy(sign, sign_print)

            def calculate_magnitude() -> None:
                negated = self._alloc_vector()
                self._negate_vector(source, negated)
                self._move_vector(negated, magnitude)

            e.if_any(sign, calculate_magnitude)

            def print_minus() -> None:
                out_char = self._alloc()
                e.set_const(out_char, ord("-"))
                e.write(out_char)

            e.if_any(sign_print, print_minus)

            digits = [self._alloc() for _ in range(self.decimal_digits)]
            for digit_cell in digits:
                self._divide_vector_by_10(magnitude, digit_cell)

            started = self._alloc()
            should_print = self._alloc()
            digit_nonzero = self._alloc()
            out_char = self._alloc()
            e.clear(started)

            for index in reversed(range(len(digits))):
                digit_cell = digits[index]
                self._nonzero(digit_cell, digit_nonzero)
                self._copy(started, should_print)
                e.if_any(digit_nonzero, lambda: e.set_const(should_print, 1))
                if index == 0:
                    e.set_const(should_print, 1)

                def print_digit(digit_cell: int = digit_cell) -> None:
                    e.set_const(started, 1)
                    self._copy(digit_cell, out_char)
                    e.add_const(out_char, ord("0"))
                    e.write(out_char)

                e.if_any(should_print, print_digit)

            e.set_const(out_char, ord("\n"))
            e.write(out_char)

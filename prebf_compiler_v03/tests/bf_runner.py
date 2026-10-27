"""Tiny Brainfuck runner used only by the project tests."""

from __future__ import annotations


def run_bf(code: str, input_text: str = "", bits: int = 8, step_limit: int = 30_000_000) -> str:
    commands = "><+-.,[]"
    code = "".join(char for char in code if char in commands)
    pairs: dict[int, int] = {}
    stack: list[int] = []
    for pos, char in enumerate(code):
        if char == "[":
            stack.append(pos)
        elif char == "]":
            if not stack:
                raise ValueError("Unexpected ']' in generated BF")
            start = stack.pop()
            pairs[start] = pos
            pairs[pos] = start
    if stack:
        raise ValueError("Unclosed '[' in generated BF")

    tape = [0] * 100_000
    pointer = 0
    ip = 0
    input_data = input_text.encode("latin-1")
    input_pos = 0
    output: list[int] = []
    steps = 0
    mask = (1 << bits) - 1

    while ip < len(code):
        steps += 1
        if steps > step_limit:
            raise RuntimeError(f"BF step limit exceeded at instruction {ip}")
        char = code[ip]
        if char == ">":
            pointer += 1
            if pointer >= len(tape):
                tape.extend([0] * len(tape))
        elif char == "<":
            pointer -= 1
            if pointer < 0:
                raise RuntimeError("Generated program moved left of tape start")
        elif char == "+":
            tape[pointer] = (tape[pointer] + 1) & mask
        elif char == "-":
            tape[pointer] = (tape[pointer] - 1) & mask
        elif char == ".":
            output.append(tape[pointer] & 0xFF)
        elif char == ",":
            if input_pos < len(input_data):
                tape[pointer] = input_data[input_pos]
                input_pos += 1
            else:
                tape[pointer] = 0
        elif char == "[" and tape[pointer] == 0:
            ip = pairs[ip]
        elif char == "]" and tape[pointer] != 0:
            ip = pairs[ip]
        ip += 1

    return bytes(output).decode("latin-1")

"""Command-line interface for the preBF compiler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compiler import compile_source
from .errors import PreBFError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prebf",
        description="Компилирует program.prebf в обычный Brainfuck program.bf.",
    )
    parser.add_argument("-i", "--input", default="program.prebf", help="исходный файл (по умолчанию program.prebf)")
    parser.add_argument("-o", "--output", default="program.bf", help="выходной файл (по умолчанию program.bf)")
    parser.add_argument("--bits", type=int, default=8, help="логическая разрядность int в битах (по умолчанию 8; каждое значение занимает ceil(bits/4) ячеек BF)")
    parser.add_argument("--max-array-size", type=int, default=64, help="резерв элементов для массивов, размер которых задан переменной (по умолчанию 64)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_path = Path(args.input)
    output_path = Path(args.output)

    try:
        source = source_path.read_text(encoding="utf-8")
        brainfuck = compile_source(source, bits=args.bits, max_array_size=args.max_array_size)
        # Atomic replacement prevents leaving a half-written result on failure.
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary.write_text(brainfuck + "\n", encoding="utf-8")
        temporary.replace(output_path)
    except (OSError, PreBFError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    print(f"Скомпилировано: {source_path} -> {output_path} (разрядность: {args.bits} бит, ячеек на число: {(args.bits + 3) // 4})")
    print(f"Размер программы: {len(brainfuck)} команд Brainfuck")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

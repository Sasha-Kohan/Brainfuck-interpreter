"""Type-aware v0.4 source lowering to the existing scalar preBF core.

The backend continues to operate on signed logical integers. ``char`` values
are normalized to their low 8 bits, ``bool`` values to zero/one, and pairs/
arrays are lowered to named scalar storage cells. Dynamic array indexing is
expanded to a set of runtime index checks against statically reserved storage.
"""

from __future__ import annotations

import ast as py_ast
import re
from dataclasses import dataclass
from typing import Callable

from .errors import PreBFError

Primitive = str
TypeSpec = Primitive | tuple[Primitive, Primitive]
_PRIMITIVES = {"int", "char", "bool"}
_TYPE_PREFIX = re.compile(
    r"^new\s+(?P<type>pair\s*<\s*(?:int|char|bool)\s*,\s*(?:int|char|bool)\s*>|int|char|bool)\s+(?P<tail>.+)$"
)
_DECL_SEGMENT = re.compile(
    r"^\s*(?P<name>[A-Za-z_]\w*)\s*(?:\[\s*(?P<size>[^\]]*)\s*\])?\s*(?:=\s*(?P<init>.+))?\s*$"
)
_ARRAY_REF = re.compile(
    r"\b(?P<name>[A-Za-z_]\w*)\s*\[\s*(?P<index>[^\]]+)\s*\]\s*(?:\.\s*(?P<field>first|second)\b)?"
)
_PAIR_FIELD = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*\.\s*(?P<field>first|second)\b")
_SIZE_REF = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*\.\s*size\s*\(\s*\)")
_CHAR_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'")


@dataclass(frozen=True, slots=True)
class Declarator:
    name: str
    size_expr: str | None
    initializer: str | None
    line: int


@dataclass(slots=True)
class Symbol:
    name: str
    type_spec: TypeSpec
    is_array: bool = False
    size_expr: str | None = None
    fixed_size: int | None = None
    capacity: int = 1
    line: int = 0

    @property
    def is_pair(self) -> bool:
        return isinstance(self.type_spec, tuple)


class TypeLowerer:
    def __init__(self, source: str, max_array_size: int = 64) -> None:
        if max_array_size < 1:
            raise ValueError("--max-array-size must be at least 1")
        self.source = source
        self.max_array_size = max_array_size
        self.symbols: dict[str, Symbol] = {}
        self.declarations: dict[int, tuple[TypeSpec, list[Declarator]]] = {}
        self.storage_types: dict[str, str] = {}
        self._temp_counter = 0
        self._all_names = set(re.findall(r"\b[A-Za-z_]\w*\b", source))
        self.prefix = "__prebf_v04_"
        while any(name.startswith(self.prefix) for name in self._all_names):
            self.prefix = "x" + self.prefix
        self._scan_declarations()
        self._build_storage_map()

    @staticmethod
    def _strip_comment(line: str) -> str:
        quote = False
        escaped = False
        for index in range(len(line) - 1):
            char = line[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == "'":
                    quote = False
            elif char == "'":
                quote = True
            elif char == "/" and line[index + 1] == "/":
                return line[:index].rstrip()
        return line.rstrip()

    @staticmethod
    def _split_top_level(text: str, delimiter: str = ",") -> list[str]:
        parts: list[str] = []
        start = 0
        depth_paren = depth_bracket = depth_brace = 0
        quote = False
        escaped = False
        for index, char in enumerate(text):
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == "'":
                    quote = False
                continue
            if char == "'":
                quote = True
            elif char == "(": depth_paren += 1
            elif char == ")": depth_paren -= 1
            elif char == "[": depth_bracket += 1
            elif char == "]": depth_bracket -= 1
            elif char == "{": depth_brace += 1
            elif char == "}": depth_brace -= 1
            elif char == delimiter and not (depth_paren or depth_bracket or depth_brace):
                parts.append(text[start:index].strip())
                start = index + 1
        parts.append(text[start:].strip())
        return parts

    @staticmethod
    def _parse_type(text: str) -> TypeSpec:
        clean = re.sub(r"\s+", "", text)
        if clean in _PRIMITIVES:
            return clean
        match = re.fullmatch(r"pair<(int|char|bool),(int|char|bool)>", clean)
        if match:
            return (match.group(1), match.group(2))
        raise PreBFError(f"Unsupported type {text!r}; v0.4 supports int, char, bool and pair<T, U>.")

    @classmethod
    def _constant_int(cls, expression: str) -> int | None:
        try:
            node = py_ast.parse(expression.strip(), mode="eval").body
        except SyntaxError:
            return None

        def evaluate(item) -> int:
            if isinstance(item, py_ast.Constant) and isinstance(item.value, int):
                return item.value
            if isinstance(item, py_ast.UnaryOp) and isinstance(item.op, (py_ast.UAdd, py_ast.USub)):
                value = evaluate(item.operand)
                return value if isinstance(item.op, py_ast.UAdd) else -value
            if isinstance(item, py_ast.BinOp) and isinstance(item.op, (py_ast.Add, py_ast.Sub, py_ast.Mult, py_ast.FloorDiv)):
                left, right = evaluate(item.left), evaluate(item.right)
                if isinstance(item.op, py_ast.Add): return left + right
                if isinstance(item.op, py_ast.Sub): return left - right
                if isinstance(item.op, py_ast.Mult): return left * right
                if right == 0: raise ValueError
                return left // right
            raise ValueError

        try:
            return evaluate(node)
        except (ValueError, ZeroDivisionError):
            return None

    @classmethod
    def _parse_typed_declaration(cls, text: str, line: int) -> tuple[TypeSpec, list[Declarator]] | None:
        match = _TYPE_PREFIX.fullmatch(text.strip())
        if not match:
            return None
        type_spec = cls._parse_type(match.group("type"))
        tail = match.group("tail")
        declarators: list[Declarator] = []
        for segment in cls._split_top_level(tail):
            parsed = _DECL_SEGMENT.fullmatch(segment)
            if not parsed:
                raise PreBFError(f"Invalid variable declaration: {segment!r}.", line)
            size_expr = parsed.group("size")
            initializer = parsed.group("init")
            if size_expr is not None and initializer is not None:
                raise PreBFError("Array declarations cannot also use a scalar initializer in v0.4.", line)
            declarators.append(Declarator(parsed.group("name"), size_expr, initializer, line))
        if not declarators:
            raise PreBFError("Expected a variable name after the type.", line)
        return type_spec, declarators

    def _register(self, symbol: Symbol) -> None:
        if symbol.name in self.symbols:
            previous = self.symbols[symbol.name]
            raise PreBFError(
                f"Variable {symbol.name!r} is declared more than once (first declaration on line {previous.line}).",
                symbol.line,
            )
        self.symbols[symbol.name] = symbol

    def _scan_declarations(self) -> None:
        lines = self.source.splitlines()
        for index, raw in enumerate(lines):
            clean = self._strip_comment(raw)
            content = clean.lstrip("\t")
            if not content:
                continue
            declaration = self._parse_typed_declaration(content, index + 1) if content.startswith("new ") else None
            if declaration is not None:
                self.declarations[index] = declaration
                type_spec, declarators = declaration
                for item in declarators:
                    fixed_size = self._constant_int(item.size_expr) if item.size_expr is not None else None
                    if item.size_expr is not None:
                        if fixed_size is not None and fixed_size < 0:
                            raise PreBFError("Array size cannot be negative.", item.line)
                        capacity = fixed_size if fixed_size is not None else self.max_array_size
                    else:
                        capacity = 1
                    self._register(Symbol(item.name, type_spec, item.size_expr is not None,
                                          item.size_expr, fixed_size, capacity, item.line))
                continue

            # Preserve declarations from v0.3 as shorthand for int variables.
            if content.startswith("new "):
                match = re.fullmatch(r"new\s+([A-Za-z_]\w*)(?:\s*=\s*(.+))?", content)
                if match:
                    self._register(Symbol(match.group(1), "int", line=index + 1))
                    continue
                word = re.match(r"new\s+([A-Za-z_]\w*)\s+", content)
                if word and (word.group(1) not in _PRIMITIVES or re.match(r"new\s+pair\b", content)):
                    raise PreBFError(f"Unknown type or malformed declaration near {word.group(1)!r}.", index + 1)

            # C++-like typed declaration in a for initializer (currently scalar).
            for_match = re.search(r"\bfor\s*\(\s*new\s+(int|char|bool)\s+([A-Za-z_]\w*)", content)
            if for_match:
                self._register(Symbol(for_match.group(2), for_match.group(1), line=index + 1))
            else:
                legacy_for = re.search(r"\bfor\s*\(\s*new\s+([A-Za-z_]\w*)", content)
                if legacy_for and legacy_for.group(1) not in _PRIMITIVES:
                    self._register(Symbol(legacy_for.group(1), "int", line=index + 1))

    def _fields(self, type_spec: TypeSpec) -> list[tuple[str, str]]:
        if isinstance(type_spec, tuple):
            return [("first", type_spec[0]), ("second", type_spec[1])]
        return [("", type_spec)]

    def _storage_name(self, symbol: Symbol, index: int | None = None, field: str = "") -> str:
        if not symbol.is_array:
            if isinstance(symbol.type_spec, tuple):
                return f"{self.prefix}{symbol.name}_{field}"
            return symbol.name
        assert index is not None
        suffix = f"_elem_{index}"
        if isinstance(symbol.type_spec, tuple):
            suffix += f"_{field}"
        return f"{self.prefix}{symbol.name}{suffix}"

    def _size_name(self, symbol: Symbol) -> str:
        return f"{self.prefix}{symbol.name}_size"

    def _build_storage_map(self) -> None:
        for symbol in self.symbols.values():
            if symbol.is_array:
                self.storage_types[self._size_name(symbol)] = "int"
                for index in range(symbol.capacity):
                    for field, type_name in self._fields(symbol.type_spec):
                        self.storage_types[self._storage_name(symbol, index, field)] = type_name
            else:
                for field, type_name in self._fields(symbol.type_spec):
                    self.storage_types[self._storage_name(symbol, field=field)] = type_name

    def _new_temp(self) -> str:
        self._temp_counter += 1
        name = f"{self.prefix}tmp_{self._temp_counter}"
        self.storage_types[name] = "int"
        return name

    @staticmethod
    def _indent(depth: int) -> str:
        return "\t" * depth

    @staticmethod
    def _char_code(value: str, line: int) -> str:
        import ast
        try:
            decoded = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise PreBFError(f"Invalid char literal {value!r}.", line) from exc
        if not isinstance(decoded, str) or len(decoded) != 1:
            raise PreBFError("A char literal must contain exactly one character.", line)
        return str(ord(decoded) & 0xFF)

    def _rewrite_literals(self, text: str, line: int) -> str:
        text = _CHAR_LITERAL.sub(lambda match: self._char_code(match.group(0), line), text)
        text = re.sub(r"\btrue\b", "1", text)
        text = re.sub(r"\bfalse\b", "0", text)
        return text

    def _element_slot(self, symbol: Symbol, index: int, field: str, line: int) -> tuple[str, str]:
        if not symbol.is_array:
            raise PreBFError(f"{symbol.name!r} is not an array.", line)
        if index < 0 or index >= symbol.capacity:
            limit = symbol.fixed_size if symbol.fixed_size is not None else symbol.capacity
            raise PreBFError(f"Array index {index} is outside the allocated range 0..{limit - 1}.", line)
        if isinstance(symbol.type_spec, tuple):
            if field not in ("first", "second"):
                raise PreBFError(f"Array {symbol.name!r} contains pairs; use .first or .second.", line)
            type_name = symbol.type_spec[0 if field == "first" else 1]
        else:
            if field:
                raise PreBFError(f"Array {symbol.name!r} does not contain pairs; .{field} is invalid.", line)
            type_name = symbol.type_spec
        if symbol.fixed_size is not None and index >= symbol.fixed_size:
            raise PreBFError(f"Array index {index} is out of bounds for {symbol.name}[{symbol.fixed_size}].", line)
        return self._storage_name(symbol, index, field), type_name

    @staticmethod
    def _looks_like_lvalue(text: str) -> bool:
        return re.fullmatch(
            r"[A-Za-z_]\w*(?:\s*\[\s*[^\]]+\s*\])?(?:\s*\.\s*(?:first|second))?",
            text.strip(),
        ) is not None

    def _resolve_lvalue(self, text: str, line: int) -> tuple[str, str, tuple[Symbol, str, str] | None]:
        text = text.strip()
        match = re.fullmatch(
            r"(?P<name>[A-Za-z_]\w*)(?:\s*\[\s*(?P<index>[^\]]+)\s*\])?(?:\s*\.\s*(?P<field>first|second))?",
            text,
        )
        if not match:
            raise PreBFError(f"Invalid variable/array target {text!r}.", line)
        name, index_text, field = match.group("name"), match.group("index"), match.group("field") or ""
        if name not in self.symbols:
            raise PreBFError(f"Unknown variable {name!r}.", line)
        symbol = self.symbols[name]
        if index_text is not None:
            if not symbol.is_array:
                raise PreBFError(f"{name!r} is not an array.", line)
            constant = self._constant_int(index_text)
            if constant is not None and symbol.fixed_size is not None:
                storage, element_type = self._element_slot(symbol, constant, field, line)
                return storage, element_type, None
            return "", "", (symbol, index_text.strip(), field)
        if symbol.is_array:
            raise PreBFError(f"Array {name!r} requires an index or .size().", line)
        if isinstance(symbol.type_spec, tuple):
            if field not in ("first", "second"):
                raise PreBFError(f"Pair {name!r} requires .first or .second.", line)
            type_name = symbol.type_spec[0 if field == "first" else 1]
            return self._storage_name(symbol, field=field), type_name, None
        if field:
            raise PreBFError(f"Variable {name!r} is not a pair.", line)
        return name, symbol.type_spec, None

    def _rewrite_expr(self, text: str, line: int, indent: int) -> tuple[list[str], str]:
        prelude: list[str] = []
        rewritten = self._rewrite_literals(text, line)

        def size_replace(match: re.Match[str]) -> str:
            name = match.group("name")
            if name not in self.symbols or not self.symbols[name].is_array:
                raise PreBFError(f"{name!r} is not an array; .size() is only available on arrays.", line)
            return self._size_name(self.symbols[name])

        rewritten = _SIZE_REF.sub(size_replace, rewritten)

        def array_replace(match: re.Match[str]) -> str:
            name, raw_index, field = match.group("name"), match.group("index").strip(), match.group("field") or ""
            if name not in self.symbols:
                raise PreBFError(f"Unknown array {name!r}.", line)
            symbol = self.symbols[name]
            if not symbol.is_array:
                raise PreBFError(f"{name!r} is not an array.", line)
            index_constant = self._constant_int(raw_index)
            if index_constant is not None and symbol.fixed_size is not None:
                return self._element_slot(symbol, index_constant, field, line)[0]
            if index_constant is not None and symbol.fixed_size is None:
                slot, _ = self._element_slot(symbol, index_constant, field, line)
                temp = self._new_temp()
                prelude.append(self._indent(indent) + f"new {temp}")
                prelude.extend([
                    self._indent(indent) + f"if {self._size_name(symbol)} > {index_constant}:",
                    self._indent(indent + 1) + f"{temp} = {slot}",
                ])
                return temp

            index_prelude, index_expr = self._rewrite_expr(raw_index, line, indent)
            prelude.extend(index_prelude)
            temp = self._new_temp()
            prelude.append(self._indent(indent) + f"new {temp}")
            for index in range(symbol.capacity):
                try:
                    slot, _ = self._element_slot(symbol, index, field, line)
                except PreBFError:
                    continue
                prefix = self._indent(indent)
                prelude.extend([
                    prefix + f"if {index_expr} == {index}:",
                    self._indent(indent + 1) + f"if {self._size_name(symbol)} > {index}:",
                    self._indent(indent + 2) + f"{temp} = {slot}",
                ])
            return temp

        rewritten = _ARRAY_REF.sub(array_replace, rewritten)

        def field_replace(match: re.Match[str]) -> str:
            name, field = match.group("name"), match.group("field")
            if name not in self.symbols:
                raise PreBFError(f"Unknown pair {name!r}.", line)
            symbol = self.symbols[name]
            if symbol.is_array or not isinstance(symbol.type_spec, tuple):
                raise PreBFError(f"{name!r} is not a scalar pair.", line)
            type_name = symbol.type_spec[0 if field == "first" else 1]
            return self._storage_name(symbol, field=field)

        rewritten = _PAIR_FIELD.sub(field_replace, rewritten)
        return prelude, rewritten

    @staticmethod
    def _split_comparison(text: str) -> tuple[str, str, str] | None:
        depth = 0
        quote = False
        escaped = False
        i = 0
        while i < len(text):
            char = text[i]
            if quote:
                if escaped: escaped = False
                elif char == "\\": escaped = True
                elif char == "'": quote = False
                i += 1
                continue
            if char == "'": quote = True; i += 1; continue
            if char == "(": depth += 1
            elif char == ")": depth -= 1
            if depth == 0:
                for op in ("==", "!=", "<=", ">=", "<", ">"):
                    if text.startswith(op, i):
                        return text[:i].strip(), op, text[i + len(op):].strip()
            i += 1
        return None

    def _emit_assignment(self, target: str, target_type: str, expression: str, line: int, indent: int) -> list[str]:
        prefix = self._indent(indent)
        comparison = self._split_comparison(expression)
        if comparison is not None:
            left, op, right = comparison
            pre_l, left = self._rewrite_expr(left, line, indent)
            pre_r, right = self._rewrite_expr(right, line, indent)
            out = pre_l + pre_r
            out += [prefix + f"if {left} {op} {right}:", self._indent(indent + 1) + f"{target} = 1",
                    prefix + "else:", self._indent(indent + 1) + f"{target} = 0"]
            if target_type == "char":
                out.append(prefix + f"truncatechar {target}")
            return out

        prelude, value = self._rewrite_expr(expression, line, indent)
        out = prelude + [prefix + f"{target} = {value}"]
        if target_type == "char":
            out.append(prefix + f"truncatechar {target}")
        elif target_type == "bool":
            out.extend([
                prefix + f"if {target} != 0:",
                self._indent(indent + 1) + f"{target} = 1",
                prefix + "else:",
                self._indent(indent + 1) + f"{target} = 0",
            ])
        return out

    def _emit_initializer(self, name: str, type_name: str, expression: str, line: int, indent: int) -> list[str]:
        return self._emit_assignment(name, type_name, expression, line, indent)

    def _emit_input(self, name: str, type_name: str, line: int, indent: int) -> list[str]:
        prefix = self._indent(indent)
        if type_name == "char":
            return [prefix + f"inputchar {name}"]
        out = [prefix + f"input {name}"]
        if type_name == "bool":
            out.extend([
                prefix + f"if {name} != 0:",
                self._indent(indent + 1) + f"{name} = 1",
                prefix + "else:",
                self._indent(indent + 1) + f"{name} = 0",
            ])
        return out

    def _emit_print(self, name: str, type_name: str, indent: int) -> list[str]:
        command = "printchar" if type_name == "char" else "print"
        return [self._indent(indent) + f"{command} {name}"]

    def _selector_blocks(self, symbol: Symbol, index_expr: str, field: str, line: int, indent: int,
                         action: Callable[[str, str, int], list[str]]) -> list[str]:
        out: list[str] = []
        prefix = self._indent(indent)
        constant = self._constant_int(index_expr)
        if constant is not None:
            slot, type_name = self._element_slot(symbol, constant, field, line)
            if symbol.fixed_size is not None:
                return action(slot, type_name, indent)
            out.append(prefix + f"if {self._size_name(symbol)} > {constant}:")
            out.extend(action(slot, type_name, indent + 1))
            return out
        for index in range(symbol.capacity):
            try:
                slot, type_name = self._element_slot(symbol, index, field, line)
            except PreBFError:
                continue
            out.append(prefix + f"if {index_expr} == {index}:")
            out.append(self._indent(indent + 1) + f"if {self._size_name(symbol)} > {index}:")
            out.extend(action(slot, type_name, indent + 2))
        return out

    def _resolve_array_lvalue(self, symbol: Symbol, raw_index: str, field: str, line: int, indent: int):
        constant = self._constant_int(raw_index)
        if constant is not None and symbol.fixed_size is not None:
            slot, type_name = self._element_slot(symbol, constant, field, line)
            return [], slot, type_name, None
        prelude, index_expr = self._rewrite_expr(raw_index, line, indent)
        return prelude, None, None, (symbol, index_expr, field)

    def _expand_declaration(self, type_spec: TypeSpec, declarators: list[Declarator], line: int, indent: int) -> list[str]:
        out: list[str] = []
        prefix = self._indent(indent)
        for item in declarators:
            symbol = self.symbols[item.name]
            if symbol.is_array:
                size_name = self._size_name(symbol)
                out.append(prefix + f"new {size_name}")
                size_expr = item.size_expr or "0"
                # Fixed sizes need no runtime expression evaluation, dynamic sizes do.
                out.extend(self._emit_assignment(size_name, "int", size_expr, item.line, indent))
                if symbol.fixed_size is None:
                    out.extend([
                        prefix + f"if {size_name} < 0:",
                        self._indent(indent + 1) + f"{size_name} = 0",
                        prefix + f"if {size_name} > {symbol.capacity}:",
                        self._indent(indent + 1) + f"{size_name} = {symbol.capacity}",
                    ])
                for index in range(symbol.capacity):
                    for field, _ in self._fields(type_spec):
                        out.append(prefix + f"new {self._storage_name(symbol, index, field)}")
                continue

            fields = self._fields(type_spec)
            for field, type_name in fields:
                storage = self._storage_name(symbol, field=field)
                out.append(prefix + f"new {storage}")
            if item.initializer is None:
                continue
            if isinstance(type_spec, tuple):
                init = item.initializer.strip()
                if not (init.startswith("{") and init.endswith("}")):
                    raise PreBFError("Pair initialization must use {first_value, second_value}.", item.line)
                values = self._split_top_level(init[1:-1])
                if len(values) != 2:
                    raise PreBFError("A pair initializer must contain exactly two values.", item.line)
                for (field, type_name), value in zip(fields, values):
                    storage = self._storage_name(symbol, field=field)
                    out.extend(self._emit_initializer(storage, type_name, value, item.line, indent))
            else:
                out.extend(self._emit_initializer(item.name, type_spec, item.initializer, item.line, indent))
        return out

    def _transform_input_or_print(self, content: str, line: int, indent: int, is_input: bool) -> list[str] | None:
        keyword = "input" if is_input else "print"
        match = re.fullmatch(rf"{keyword}\s+(.+)", content)
        if not match:
            if content.startswith(keyword + " "):
                raise PreBFError(f"Invalid {keyword} target.", line)
            return None
        target_text = match.group(1).strip()
        size_match = re.fullmatch(r"([A-Za-z_]\w*)\s*\.\s*size\s*\(\s*\)", target_text)
        if size_match:
            if is_input:
                raise PreBFError("Array .size() is read-only and cannot be an input target.", line)
            array_name = size_match.group(1)
            if array_name not in self.symbols or not self.symbols[array_name].is_array:
                raise PreBFError(f"{array_name!r} is not an array; .size() is only available on arrays.", line)
            return self._emit_print(self._size_name(self.symbols[array_name]), "int", indent)
        try:
            direct, type_name, dynamic = self._resolve_lvalue(target_text, line)
        except PreBFError:
            if self._looks_like_lvalue(target_text):
                raise
            if not is_input:
                temp = self._new_temp()
                prefix = self._indent(indent)
                return [prefix + f"new {temp}"] + self._emit_assignment(temp, "int", target_text, line, indent) + self._emit_print(temp, "int", indent)
            raise PreBFError("input expects a variable, pair field, or array element.", line)
        if dynamic is None:
            return self._emit_input(direct, type_name, line, indent) if is_input else self._emit_print(direct, type_name, indent)
        symbol, raw_index, field = dynamic
        prelude, _, _, dyn = self._resolve_array_lvalue(symbol, raw_index, field, line, indent)
        assert dyn is not None
        _, index_expr, _ = dyn
        out = list(prelude)
        if is_input:
            out.extend(self._selector_blocks(symbol, index_expr, field, line, indent,
                                             lambda slot, typ, depth: self._emit_input(slot, typ, line, depth)))
        else:
            out.extend(self._selector_blocks(symbol, index_expr, field, line, indent,
                                             lambda slot, typ, depth: self._emit_print(slot, typ, depth)))
        return out

    def _transform_assignment(self, content: str, line: int, indent: int) -> list[str] | None:
        # Postfix and compound forms also work for individual array/pair fields.
        postfix = re.fullmatch(r"(.+?)(\+\+|--)", content)
        compound = re.fullmatch(r"(.+?)\s*(\+=|-=)\s*(.+)", content)
        assignment = re.fullmatch(r"(.+?)\s*=\s*(?!=)(.+)", content)
        if postfix:
            target_text, operator, value = postfix.group(1).strip(), ("+" if postfix.group(2) == "++" else "-"), "1"
        elif compound:
            target_text, operator, value = compound.group(1).strip(), ("+" if compound.group(2) == "+=" else "-"), compound.group(3).strip()
        elif assignment:
            target_text, operator, value = assignment.group(1).strip(), "", assignment.group(2).strip()
        else:
            return None
        # Do not confuse comparisons and control-flow headers with assignments.
        if target_text.startswith(("if ", "else ", "while ", "for ")):
            return None
        try:
            direct, type_name, dynamic = self._resolve_lvalue(target_text, line)
        except PreBFError:
            if self._looks_like_lvalue(target_text):
                raise
            return None

        def assign_to(slot: str, typ: str, depth: int, rhs: str = value) -> list[str]:
            expr = f"{slot} {operator} ({rhs})" if operator else rhs
            return self._emit_assignment(slot, typ, expr, line, depth)

        if dynamic is None:
            return assign_to(direct, type_name, indent)
        symbol, raw_index, field = dynamic
        prelude, _, _, dyn = self._resolve_array_lvalue(symbol, raw_index, field, line, indent)
        assert dyn is not None
        _, index_expr, _ = dyn
        out = list(prelude)
        out.extend(self._selector_blocks(symbol, index_expr, field, line, indent,
                                         lambda slot, typ, depth: assign_to(slot, typ, depth)))
        return out

    def _rewrite_condition(self, content: str, line: int, indent: int) -> tuple[list[str], str]:
        comparison = self._split_comparison(content)
        if comparison is None:
            return self._rewrite_expr(content, line, indent)
        left, op, right = comparison
        pre_left, left = self._rewrite_expr(left, line, indent)
        pre_right, right = self._rewrite_expr(right, line, indent)
        return pre_left + pre_right, f"{left} {op} {right}"

    def _transform_for_header(self, content: str, line: int, indent: int) -> list[str]:
        match = re.fullmatch(r"for\s*\((.*)\)\s*:", content)
        if not match:
            raise PreBFError("Expected for (init; condition; update):.", line)
        parts = self._split_top_level(match.group(1), delimiter=";")
        if len(parts) != 3:
            raise PreBFError("A for header must contain two semicolons.", line)
        init, condition, update = (part.strip() for part in parts)
        if init.startswith("new "):
            typed = re.fullmatch(r"new\s+(int|char|bool)\s+([A-Za-z_]\w*)(?:\s*=\s*(.+))?", init)
            if typed:
                type_name, name, value = typed.groups()
                if type_name != "int":
                    raise PreBFError("A for-loop declaration currently supports int variables; declare char/bool before the loop.", line)
                init = f"new {name}" + (f" = {value}" if value is not None else "")
            else:
                init = re.sub(r"\bnew\s+pair\s*<[^>]+>\s+", "new ", init)
        if init:
            init_match = re.fullmatch(r"new\s+([A-Za-z_]\w*)\s*(?:=\s*(.+))?", init)
            if init_match and init_match.group(2) is not None:
                pre, expr = self._rewrite_expr(init_match.group(2), line, indent)
                if pre:
                    raise PreBFError("Dynamic array indexing in a for-loop initializer is not supported; initialize it before the loop.", line)
                init = f"new {init_match.group(1)} = {expr}"
            else:
                init = self._rewrite_inline_simple(init, line, indent)
        if condition:
            pre, condition = self._rewrite_condition(condition, line, indent)
            if pre:
                raise PreBFError("Dynamic array indexing in a for condition is not supported; use an integer loop variable.", line)
        if update:
            update = self._rewrite_inline_simple(update, line, indent)
        return [self._indent(indent) + f"for ({init}; {condition}; {update}):"]

    def _rewrite_inline_simple(self, text: str, line: int, indent: int) -> str:
        postfix = re.fullmatch(r"([A-Za-z_]\w*)(\+\+|--)", text)
        if postfix:
            return text
        compound = re.fullmatch(r"([A-Za-z_]\w*)\s*(\+=|-=)\s*(.+)", text)
        if compound:
            pre, rhs = self._rewrite_expr(compound.group(3), line, indent)
            if pre:
                raise PreBFError("Dynamic array indexing in a for update is not supported.", line)
            return f"{compound.group(1)} {compound.group(2)} {rhs}"
        assignment = re.fullmatch(r"([A-Za-z_]\w*)\s*=\s*(.+)", text)
        if assignment:
            pre, rhs = self._rewrite_expr(assignment.group(2), line, indent)
            if pre:
                raise PreBFError("Dynamic array indexing in a for update is not supported.", line)
            return f"{assignment.group(1)} = {rhs}"
        return text

    def lower(self) -> str:
        output: list[str] = []
        for line_index, raw in enumerate(self.source.splitlines()):
            clean = self._strip_comment(raw)
            if not clean.strip():
                output.append("")
                continue
            indent = len(clean) - len(clean.lstrip("\t"))
            content = clean[indent:]
            if line_index in self.declarations:
                type_spec, declarators = self.declarations[line_index]
                output.extend(self._expand_declaration(type_spec, declarators, line_index + 1, indent))
                continue

            # Inline declaration in a for initializer gets its type keyword removed.
            if content.startswith("for "):
                output.extend(self._transform_for_header(content, line_index + 1, indent))
                continue

            # Legacy scalar declaration is already registered, but its initializer
            # must pass through typed conversions as well.
            legacy_new = re.fullmatch(r"new\s+([A-Za-z_]\w*)(?:\s*=\s*(.+))?", content)
            if legacy_new and legacy_new.group(1) in self.symbols:
                name, initializer = legacy_new.groups()
                output.append(self._indent(indent) + f"new {name}")
                if initializer is not None:
                    output.extend(self._emit_initializer(name, "int", initializer, line_index + 1, indent))
                continue

            input_or_print = self._transform_input_or_print(content, line_index + 1, indent, True)
            if input_or_print is not None:
                output.extend(input_or_print)
                continue
            input_or_print = self._transform_input_or_print(content, line_index + 1, indent, False)
            if input_or_print is not None:
                output.extend(input_or_print)
                continue

            # Conditions may contain dynamic array reads; prelude is executed on
            # each ordinary if-entry. Else-if chains cannot be interrupted.
            condition_match = re.fullmatch(r"(if|else if)\s+(.+)\s*:", content)
            if condition_match:
                kind, condition_text = condition_match.groups()
                prelude, condition = self._rewrite_condition(condition_text, line_index + 1, indent)
                if kind == "else if" and prelude:
                    raise PreBFError("Dynamic array indexing in an else-if condition is not supported; use a temporary variable.", line_index + 1)
                output.extend(prelude)
                output.append(self._indent(indent) + f"{kind} {condition}:")
                continue

            while_match = re.fullmatch(r"while\s+(.+)\s*:", content)
            if while_match:
                prelude, condition = self._rewrite_condition(while_match.group(1), line_index + 1, indent)
                if prelude:
                    raise PreBFError("Dynamic array indexing in a while condition is not supported; use a temporary variable.", line_index + 1)
                output.append(self._indent(indent) + f"while {condition}:")
                continue

            assignment = self._transform_assignment(content, line_index + 1, indent)
            if assignment is not None:
                output.extend(assignment)
                continue

            # Preserve block markers and pass comments/blank lines through.
            if content in ("else:",):
                output.append(self._indent(indent) + content)
            elif content.startswith("output("):
                legacy = re.fullmatch(r"output\s*\(\s*([A-Za-z_]\w*)\s*\)", content)
                if legacy:
                    output.extend(self._transform_input_or_print("print " + legacy.group(1), line_index + 1, indent, False) or [])
                else:
                    raise PreBFError("Invalid output target.", line_index + 1)
            else:
                output.append(self._indent(indent) + content)
        return "\n".join(output) + "\n"


def lower_typed_source(source: str, max_array_size: int = 64) -> str:
    """Lower v0.4 typed variables, pairs, arrays, and conversions to core preBF."""
    return TypeLowerer(source, max_array_size=max_array_size).lower()

"""A compact compiler for the supported CSS selector subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

_IDENT = re.compile(r"[-_a-zA-Z][-_a-zA-Z0-9]*")
_ATTR = re.compile(
    r"""^\s*([-_a-zA-Z][-_a-zA-Z0-9]*)\s*
        (?:
          (\^=|\$=|\*=|~=|\|=|=)\s*
          (?:"([^"]*)"|'([^']*)'|([^\s]+?))
          (?:\s+([iIsS]))?
        )?\s*$""",
    re.X,
)

H_ID = 5863474
H_CLASS = 210708946651


class SelectorError(ValueError):
    pass


def name_hash(value: str) -> int:
    result = 5381
    for byte in value.lower().encode("utf-8"):
        result = (result * 33 + byte) & 0x7FFF_FFFF_FFFF_FFFF
    return result


def _split_top_level(query: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    square = paren = 0
    quote = ""
    for i, char in enumerate(query):
        if quote:
            if char == quote and (i == 0 or query[i - 1] != "\\"):
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "[":
            square += 1
        elif char == "]":
            square -= 1
        elif char == "(":
            paren += 1
        elif char == ")":
            paren -= 1
        elif char == delimiter and square == 0 and paren == 0:
            parts.append(query[start:i].strip())
            start = i + 1
    parts.append(query[start:].strip())
    if square or paren or quote or any(not part for part in parts):
        raise SelectorError(f"invalid CSS selector: {query!r}")
    return parts


def _split_chain(group: str) -> tuple[list[str], list[int]]:
    compounds: list[str] = []
    combinators: list[int] = []
    pos = 0
    length = len(group)
    while pos < length:
        while pos < length and group[pos].isspace():
            pos += 1
        start = pos
        square = paren = 0
        quote = ""
        while pos < length:
            char = group[pos]
            if quote:
                if char == quote and group[pos - 1] != "\\":
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "[":
                square += 1
            elif char == "]":
                square -= 1
            elif char == "(":
                paren += 1
            elif char == ")":
                paren -= 1
            elif square == 0 and paren == 0 and (char.isspace() or char in ">+~"):
                break
            pos += 1
        compound = group[start:pos]
        if not compound:
            raise SelectorError(f"invalid CSS selector near {group[pos:]!r}")
        compounds.append(compound)
        had_space = False
        while pos < length and group[pos].isspace():
            had_space = True
            pos += 1
        if pos >= length:
            break
        if group[pos] in ">+~":
            combinators.append({">": 2, "+": 3, "~": 4}[group[pos]])
            pos += 1
        elif had_space:
            combinators.append(1)
        else:
            raise SelectorError(f"invalid CSS selector near {group[pos:]!r}")
    if len(combinators) != len(compounds) - 1:
        raise SelectorError(f"invalid CSS selector: {group!r}")
    return compounds, combinators


def _nth(value: str) -> tuple[int, int]:
    value = re.sub(r"\s+", "", value.lower())
    if value == "odd":
        return 2, 1
    if value == "even":
        return 2, 0
    if "n" not in value:
        try:
            return 0, int(value)
        except ValueError as exc:
            raise SelectorError(f"invalid nth expression: {value!r}") from exc
    left, right = value.split("n", 1)
    if left in ("", "+"):
        a = 1
    elif left == "-":
        a = -1
    else:
        try:
            a = int(left)
        except ValueError as exc:
            raise SelectorError(f"invalid nth expression: {value!r}") from exc
    try:
        b = int(right or "0")
    except ValueError as exc:
        raise SelectorError(f"invalid nth expression: {value!r}") from exc
    return a, b


@dataclass
class CompiledSelector:
    steps: np.ndarray
    groups: np.ndarray
    conditions: np.ndarray
    values: np.ndarray
    addresses: tuple[int, int, int, int]


class _Compiler:
    def __init__(self) -> None:
        self.conditions: list[list[int]] = []
        self.values = bytearray()

    def value(self, value: str) -> tuple[int, int]:
        encoded = value.encode("utf-8")
        start = len(self.values)
        self.values.extend(encoded)
        return start, len(encoded)

    def add(self, op: int, arg: int = 0, value: str = "", a: int = 0, b: int = 0) -> None:
        start, length = self.value(value)
        self.conditions.append([op, arg, start, length, a, b])

    def compound(self, text: str) -> tuple[int, int]:
        begin = len(self.conditions)
        pos = 0
        if text.startswith("*"):
            pos = 1
        else:
            match = _IDENT.match(text)
            if match:
                self.add(1, name_hash(match.group()))
                pos = match.end()
        while pos < len(text):
            char = text[pos]
            if char in "#.":
                match = _IDENT.match(text, pos + 1)
                if not match:
                    raise SelectorError(f"invalid name in {text!r}")
                if char == "#":
                    self.add(3, H_ID, match.group())
                else:
                    self.add(7, H_CLASS, match.group())
                pos = match.end()
                continue
            if char == "[":
                end = pos + 1
                quote = ""
                while end < len(text):
                    if quote:
                        if text[end] == quote:
                            quote = ""
                    elif text[end] in "\"'":
                        quote = text[end]
                    elif text[end] == "]":
                        break
                    end += 1
                if end >= len(text):
                    raise SelectorError(f"unterminated attribute selector in {text!r}")
                match = _ATTR.match(text[pos + 1 : end])
                if not match:
                    raise SelectorError(f"invalid attribute selector in {text!r}")
                name, operator = match.group(1), match.group(2)
                value = next((part for part in match.group(3, 4, 5) if part is not None), "")
                flag = (match.group(6) or "").lower()
                if not operator:
                    self.add(2, name_hash(name))
                else:
                    op = {"=": 3, "^=": 4, "$=": 5, "*=": 6, "~=": 7, "|=": 8}[operator]
                    if flag == "i":
                        if operator != "=":
                            raise SelectorError("case-insensitive flags are currently supported for '=' only")
                        op = 9
                    self.add(op, name_hash(name), value)
                pos = end + 1
                continue
            if char == ":":
                match = _IDENT.match(text, pos + 1)
                if not match:
                    raise SelectorError(f"invalid pseudo-class in {text!r}")
                name = match.group().lower()
                pos = match.end()
                argument = None
                if pos < len(text) and text[pos] == "(":
                    depth = 1
                    end = pos + 1
                    quote = ""
                    while end < len(text) and depth:
                        c = text[end]
                        if quote:
                            if c == quote:
                                quote = ""
                        elif c in "\"'":
                            quote = c
                        elif c == "(":
                            depth += 1
                        elif c == ")":
                            depth -= 1
                        end += 1
                    if depth:
                        raise SelectorError(f"unterminated pseudo-class in {text!r}")
                    argument = text[pos + 1 : end - 1].strip()
                    pos = end
                simple = {
                    "first-child": 20,
                    "last-child": 21,
                    "only-child": 22,
                    "first-of-type": 24,
                    "last-of-type": 25,
                    "only-of-type": 26,
                    "empty": 28,
                    "root": 29,
                }
                if name in simple and argument is None:
                    self.add(simple[name])
                elif name in ("nth-child", "nth-of-type") and argument is not None:
                    a, b = _nth(argument)
                    self.add(23 if name == "nth-child" else 27, a=a, b=b)
                elif name == "not" and argument is not None:
                    nested_start = len(self.conditions)
                    self.compound(argument)
                    if len(self.conditions) != nested_start + 1:
                        del self.conditions[nested_start:]
                        raise SelectorError(":not() currently accepts one simple selector")
                    self.conditions[-1][0] *= -1
                else:
                    raise SelectorError(f"unsupported pseudo-class: :{name}")
                continue
            raise SelectorError(f"unsupported CSS syntax near {text[pos:]!r}")
        return begin, len(self.conditions) - begin


@lru_cache(maxsize=256)
def compile_selector(query: str) -> CompiledSelector:
    if not isinstance(query, str) or not query.strip():
        raise SelectorError("CSS selector must be a non-empty string")
    compiler = _Compiler()
    steps: list[list[int]] = []
    groups: list[list[int]] = []
    for group_text in _split_top_level(query, ","):
        compounds, combinators = _split_chain(group_text)
        group_start = len(steps)
        for index in range(len(compounds) - 1, -1, -1):
            condition_start, condition_count = compiler.compound(compounds[index])
            relation = combinators[index - 1] if index else 0
            steps.append([condition_start, condition_count, relation])
        groups.append([group_start, len(compounds)])
    values = np.frombuffer(bytes(compiler.values) or b"\0", dtype=np.uint8)
    condition_rows = compiler.conditions or [[0] * 6]
    step_array = np.ascontiguousarray(steps, dtype=np.int64)
    group_array = np.ascontiguousarray(groups, dtype=np.int64)
    condition_array = np.ascontiguousarray(condition_rows, dtype=np.int64)
    arrays = (step_array, group_array, condition_array, values)
    for array in arrays:
        array.flags.writeable = False
    return CompiledSelector(
        step_array,
        group_array,
        condition_array,
        values,
        tuple(int(array.ctypes.data) for array in arrays),
    )

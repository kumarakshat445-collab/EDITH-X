"""SystemVerilog parsing helpers used by analysis, generation, and debug."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class Port:
    direction: str
    name: str
    width: str | None
    signed: bool
    datatype: str


@dataclass
class Module:
    name: str
    parameters: list[tuple[str, str]]
    ports: list[Port]
    start: int
    end: int
    spec: dict = field(default_factory=dict)


def mask_comments(src: str) -> str:
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        if src.startswith("//", i):
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
        elif src.startswith("/*", i):
            out.extend("  ")
            i += 2
            while i < n and not src.startswith("*/", i):
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            if src.startswith("*/", i):
                out.extend("  ")
                i += 2
        elif src[i] == '"':
            out.append('"')
            i += 1
            while i < n and src[i] not in '"\n':
                out.append(src[i])
                i += 1
            if i < n and src[i] == '"':
                out.append('"')
                i += 1
        else:
            out.append(src[i])
            i += 1
    return "".join(out)


def line_of(src: str, index: int) -> int:
    return src.count("\n", 0, index) + 1


def balanced(src: str, index: int, open_c: str = "(", close_c: str = ")") -> tuple[str, int]:
    if index >= len(src) or src[index] != open_c:
        raise ValueError("Expected delimiter.")
    depth = 0
    j = index
    while j < len(src):
        ch = src[j]
        if ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth == 0:
                return src[index + 1 : j], j + 1
        j += 1
    raise ValueError("Unbalanced delimiter.")


def read_spec(src: str) -> dict:
    match = re.search(r"@hexa-spec\s+(\{.*\})", src)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _split_top(text: str, sep: str = ",") -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _parse_port(chunk: str) -> Port | None:
    match = re.search(r"\b(input|output|inout)\b", chunk)
    if not match:
        return None
    direction = match.group(1)
    rest = chunk[match.end() :]
    datatype = "logic"
    dtype = re.search(r"\b(wire|reg|logic|bit|int|integer|byte)\b", rest)
    if dtype:
        datatype = dtype.group(1)
    signed = bool(re.search(r"\bsigned\b", rest))
    width_match = re.search(r"\[[^\]]+\]", rest)
    width = width_match.group(0) if width_match else None
    names = re.findall(r"\b([A-Za-z_]\w*)\b", rest)
    keywords = {"wire", "reg", "logic", "bit", "int", "integer", "byte", "signed", "unsigned", "input", "output", "inout"}
    idents = [n for n in names if n not in keywords]
    if not idents:
        return None
    return Port(direction, idents[-1], width, signed, datatype)


def parse_modules(src: str) -> list[Module]:
    masked = mask_comments(src)
    spec = read_spec(src)
    modules: list[Module] = []
    for match in re.finditer(r"\bmodule\s+([A-Za-z_]\w*)", masked):
        name = match.group(1)
        i = match.end()
        while i < len(masked) and masked[i].isspace():
            i += 1
        parameters: list[tuple[str, str]] = []
        if i < len(masked) and masked[i] == "#":
            i += 1
            while i < len(masked) and masked[i].isspace():
                i += 1
            if i < len(masked) and masked[i] == "(":
                param_text, i = balanced(masked, i)
                for param in re.finditer(
                    r"\bparameter\s+(?:int|integer|logic|bit|type)?\s*([A-Za-z_]\w*)\s*=\s*([^,]+)",
                    param_text,
                ):
                    parameters.append((param.group(1), param.group(2).strip()))
                while i < len(masked) and masked[i].isspace():
                    i += 1
        ports: list[Port] = []
        if i < len(masked) and masked[i] == "(":
            port_text, i = balanced(masked, i)
            for chunk in _split_top(port_text):
                port = _parse_port(chunk)
                if port:
                    ports.append(port)
        end = re.search(r"\bendmodule\b", masked[i:])
        end_index = i + end.end() if end else len(masked)
        modules.append(
            Module(
                name=name,
                parameters=parameters,
                ports=ports,
                start=line_of(src, match.start()),
                end=line_of(src, end_index - 1),
                spec=spec,
            )
        )
    return modules


def numeric_width(width: str | None) -> int | None:
    if not width:
        return 1
    match = re.fullmatch(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", width.strip())
    if not match:
        return None
    return abs(int(match.group(1)) - int(match.group(2))) + 1


def is_clock(name: str) -> bool:
    return name.lower() in {"clk", "clock", "clk_i", "clock_i"}


def is_reset(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"rst", "reset", "rst_n", "reset_n", "rstn", "rst_ni", "resetn"}


def active_low_reset(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith("_n") or lowered.endswith("n") and "rst" in lowered

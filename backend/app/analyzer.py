"""Deterministic SystemVerilog static checks.

Diagnostics always include severity, file, line, the problem, why it matters,
and a concrete edit. Rules that need a simulator are left to the simulator.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .sv import line_of, mask_comments, numeric_width, parse_modules

_DECL_TYPES = r"logic|wire|reg|bit|int|integer|byte|genvar"


@dataclass
class Diagnostic:
    severity: str
    file: str
    line: int
    problem: str
    why: str
    fix: str
    rule: str

    def as_dict(self) -> dict:
        return asdict(self)


def analyze_source(path: str, src: str) -> list[Diagnostic]:
    masked = mask_comments(src)
    diags: list[Diagnostic] = []
    rtl = _is_rtl(path)
    diags.extend(_structure(path, src, masked))
    diags.extend(_delays_and_initial(path, masked, rtl))
    diags.extend(_always_style(path, src, masked))
    diags.extend(_assignments(path, src, masked))
    diags.extend(_case_defaults(path, masked))
    return diags


def _is_rtl(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    name = lowered.rsplit("/", 1)[-1]
    if "/tb/" in f"/{lowered}" or name.endswith("_tb.sv") or name.endswith("_tb.v"):
        return False
    if "/tests/" in f"/{lowered}":
        return False
    return True


def _structure(path: str, src: str, masked: str) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    pairs = [("module", "endmodule"), ("begin", "end"), ("case", "endcase"), ("function", "endfunction"), ("task", "endtask")]
    for open_kw, close_kw in pairs:
        opens = len(re.findall(rf"\b{open_kw}\b", masked))
        closes = len(re.findall(rf"\b{close_kw}\b", masked))
        if opens != closes:
            diags.append(
                Diagnostic(
                    "error",
                    path,
                    src.count("\n") + 1,
                    f"Unmatched {open_kw}/{close_kw} ({opens} vs {closes}).",
                    "The parser cannot trust block boundaries, so later checks and simulation will fail.",
                    f"Add the missing {close_kw if opens > closes else open_kw} so the counts match.",
                    "structure",
                )
            )
    modules = parse_modules(src)
    if re.search(r"\bmodule\b", masked) and not modules:
        diags.append(
            Diagnostic(
                "error",
                path,
                1,
                "Module header could not be parsed.",
                "Ports and parameters are unreadable, so testbench generation has nothing to connect.",
                "Use an ANSI port list: module name #(...)( input logic clk, ...);",
                "ports",
            )
        )
    body_start = 0
    if modules:
        header_end = re.search(r"\)\s*;", masked)
        body_start = header_end.end() if header_end else 0
    body = masked[body_start:]
    for match in re.finditer(rf"^\s*(?:{_DECL_TYPES})\b[^;{{]*$", body, re.M):
        line = body[: match.start()].count("\n") + masked[:body_start].count("\n") + 1
        text = match.group(0).strip()
        if text.endswith(",") or text.endswith("("):
            continue
        diags.append(
            Diagnostic(
                "error",
                path,
                line,
                "Declaration does not end with a semicolon.",
                "SystemVerilog declarations are statements. A missing semicolon shifts every later token.",
                f"Terminate `{text}` with a semicolon.",
                "semicolon",
            )
        )
    return diags


def _delays_and_initial(path: str, masked: str, rtl: bool) -> list[Diagnostic]:
    if not rtl:
        return []
    diags: list[Diagnostic] = []
    for match in re.finditer(r"#\s*\d+", masked):
        diags.append(
            Diagnostic(
                "warning",
                path,
                line_of(masked, match.start()),
                f"Delay {match.group(0).replace(' ', '')} inside synthesizable RTL.",
                "Delay controls are ignored or rejected by synthesis. The silicon will not wait #N.",
                "Remove the delay and express the wait as clocked state.",
                "delay",
            )
        )
    for match in re.finditer(r"\binitial\b", masked):
        diags.append(
            Diagnostic(
                "warning",
                path,
                line_of(masked, match.start()),
                "initial block in an RTL file.",
                "initial procedures are not a reliable reset in FPGA or ASIC synthesis.",
                "Initialize state in an always_ff block under reset.",
                "initial",
            )
        )
    for match in re.finditer(r"\bforever\b", masked):
        diags.append(
            Diagnostic(
                "warning",
                path,
                line_of(masked, match.start()),
                "forever loop in an RTL file.",
                "An unbounded loop is not a synthesizable hardware process.",
                "Move the loop into a testbench, or use a clocked state machine.",
                "forever",
            )
        )
    return diags


def _extract_blocks(masked: str, kind_re: str) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    for match in re.finditer(kind_re, masked):
        start = match.end()
        rest = masked[start:]
        begin = re.search(r"\bbegin\b", rest)
        semi = rest.find(";")
        if begin and (semi == -1 or begin.start() < semi):
            depth = 0
            j = start + begin.start()
            while j < len(masked):
                if re.match(r"\bbegin\b", masked[j:]):
                    depth += 1
                    j += 5
                    continue
                if re.match(r"\bend\b", masked[j:]):
                    depth -= 1
                    j += 3
                    if depth == 0:
                        found.append((line_of(masked, match.start()), match.group(0), masked[start:j]))
                        break
                    continue
                j += 1
        elif semi != -1:
            found.append((line_of(masked, match.start()), match.group(0), rest[: semi + 1]))
    return found


def _assigned_targets(text: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*(?:<=|=)(?!=)", text):
        name = match.group(1)
        if name in {"if", "for", "assign"}:
            continue
        names.add(name)
    return names


def _partial_targets(text: str) -> set[str]:
    """Signals assigned on some paths of a combinational block but not all."""
    partial: set[str] = set()

    def walk(block: str, inherited: set[str]) -> set[str]:
        assigned = set(inherited)
        depth = 0
        i = 0
        token = ""
        while i < len(block):
            if re.match(r"\bbegin\b", block[i:]) and depth == 0:
                # handled by the caller when the block itself is a begin/end body
                pass
            if block[i] in "([{":
                depth += 1
                i += 1
                continue
            if block[i] in ")]}":
                depth = max(0, depth - 1)
                i += 1
                continue
            if depth == 0 and re.match(r"\bif\s*\(", block[i:]):
                cond_start = block.find("(", i)
                try:
                    from .sv import balanced

                    _, after = balanced(block, cond_start)
                except ValueError:
                    break
                then_text, then_end = _grab_stmt(block, after)
                else_text = ""
                else_end = then_end
                m_else = re.match(r"\s*\belse\b", block[then_end:])
                if m_else:
                    else_text, else_rel = _grab_stmt(block, then_end + m_else.end())
                    else_end = then_end + m_else.end() + (else_rel - (then_end + m_else.end()))
                    # _grab_stmt returns absolute end index
                    else_end = else_rel
                then_set = walk(then_text, set())
                else_set = walk(else_text, set()) if else_text else set()
                both = then_set & else_set
                only = (then_set | else_set) - both
                if not else_text:
                    only = then_set
                partial.update(name for name in only if name not in assigned)
                assigned.update(both if else_text else set())
                i = else_end
                continue
            if depth == 0 and re.match(r"\bcase\b", block[i:]):
                end = re.search(r"\bendcase\b", block[i:])
                if not end:
                    break
                case_body = block[i : i + end.end()]
                branches = re.split(r"(?:^|\n)\s*(?:default\s*:|[^\n]*:)", case_body)
                branch_sets = [walk(b, set()) for b in branches if b.strip()]
                has_default = bool(re.search(r"\bdefault\s*:", case_body))
                if branch_sets:
                    common = set.intersection(*branch_sets) if has_default else set()
                    union = set.union(*branch_sets)
                    partial.update(name for name in union - common if name not in assigned)
                    assigned.update(common)
                i += end.end()
                continue
            m_asg = re.match(r"\s*([A-Za-z_]\w*)\s*(?:<=|=)(?!=)", block[i:])
            if depth == 0 and m_asg and m_asg.group(1) not in {"if", "for", "unique", "priority"}:
                assigned.add(m_asg.group(1))
            i += 1
        return assigned

    walk(_strip_outer_begin(text), set())
    return partial


def _strip_outer_begin(text: str) -> str:
    match = re.search(r"\bbegin\b(.*)\bend\b", text, re.S)
    return match.group(1) if match else text


def _grab_stmt(text: str, index: int) -> tuple[str, int]:
    while index < len(text) and text[index].isspace():
        index += 1
    if re.match(r"\bbegin\b", text[index:]):
        depth = 0
        j = index
        while j < len(text):
            if re.match(r"\bbegin\b", text[j:]):
                depth += 1
                j += 5
                continue
            if re.match(r"\bend\b", text[j:]):
                depth -= 1
                j += 3
                if depth == 0:
                    return text[index:j], j
                continue
            j += 1
        return text[index:], len(text)
    semi = text.find(";", index)
    if semi == -1:
        return text[index:], len(text)
    return text[index : semi + 1], semi + 1


def _always_style(path: str, src: str, masked: str) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    seq = _extract_blocks(masked, r"\balways_ff\b[^\n;]*|\balways\s*@\s*\([^)]*(?:pos|neg)edge[^)]*\)")
    comb = _extract_blocks(masked, r"\balways_comb\b|\balways\s*@\s*\(\s*\*\s*\)|\balways\s*@\*")
    for line, header, body in seq:
        if len(re.findall(r"\b(?:pos|neg)edge\b", header)) > 2:
            diags.append(
                Diagnostic(
                    "warning",
                    path,
                    line,
                    "More than two edge events in one sensitivity list.",
                    "Synthesis accepts a clock and at most one async reset. Extra edges infer broken clocking.",
                    "Keep only the clock, or the clock plus one asynchronous reset.",
                    "clock",
                )
            )
        for match in re.finditer(r"(?m)^(?![ \t]*for\b)([^\n]*\b[A-Za-z_]\w*\s*=(?!=)[^\n]*)", body):
            snippet = match.group(1).strip()
            if "<=" in snippet or snippet.startswith("if") or "==" in snippet:
                continue
            diags.append(
                Diagnostic(
                    "warning",
                    path,
                    line + body[: match.start()].count("\n"),
                    "Blocking assignment in sequential logic.",
                    "Blocking writes in a clocked process race with other processes that read the same signal.",
                    "Use a non-blocking assignment (`<=`) for flops.",
                    "blocking-seq",
                )
            )
    for line, _header, body in comb:
        if "<=" in body:
            diags.append(
                Diagnostic(
                    "warning",
                    path,
                    line,
                    "Non-blocking assignment in combinational logic.",
                    "NBA in always_comb schedules a later update and can infer storage or a sim/synth mismatch.",
                    "Use blocking assignments (`=`) inside always_comb.",
                    "nba-comb",
                )
            )
        for name in sorted(_partial_targets(body)):
            diags.append(
                Diagnostic(
                    "warning",
                    path,
                    line,
                    f'Potential latch inference on "{name}".',
                    f'Signal "{name}" is not assigned on every path through this combinational process.',
                    f'Assign a default to "{name}" before the conditional, or complete every branch.',
                    "latch",
                )
            )
    return diags


def _case_defaults(path: str, masked: str) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for match in re.finditer(r"\bcase\b(?!z)(?!x)", masked):
        end = re.search(r"\bendcase\b", masked[match.end() :])
        if not end:
            continue
        body = masked[match.end() : match.end() + end.start()]
        if not re.search(r"\bdefault\s*:", body):
            diags.append(
                Diagnostic(
                    "warning",
                    path,
                    line_of(masked, match.start()),
                    "case has no default branch.",
                    "Unspecified encodings hold the previous value and infer a latch, or they match unintended X.",
                    "Add a default assignment that drives a defined value.",
                    "case-default",
                )
            )
    return diags


def _assignments(path: str, src: str, masked: str) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    modules = parse_modules(src)
    ports = {p.name for m in modules for p in m.ports}
    declared: dict[str, tuple[int, int | None, bool]] = {}
    decl_re = re.compile(
        rf"\b(?P<signed>signed\s+)?(?:{_DECL_TYPES})\b\s*(?P<width>\[[^\]]+\])?\s*(?P<name>[A-Za-z_]\w*)"
    )
    skip_names = {"unsigned", "signed", "input", "output", "inout", "const", "static"}
    for match in decl_re.finditer(masked):
        if match.group("name") in skip_names:
            continue
        declared[match.group("name")] = (
            line_of(masked, match.start()),
            numeric_width(match.group("width")),
            bool(match.group("signed")),
        )
    drivers: dict[str, list[int]] = {}
    regions = _extract_blocks(masked, r"\balways(?:_ff|_comb|_latch)?\b[^\n]*")
    for line, _header, body in regions:
        for name in _assigned_targets(body):
            drivers.setdefault(name, []).append(line)
    for match in re.finditer(r"\bassign\s+([A-Za-z_]\w*)\s*=", masked):
        drivers.setdefault(match.group(1), []).append(line_of(masked, match.start()))
        rhs_end = masked.find(";", match.end())
        rhs = masked[match.end() : rhs_end if rhs_end != -1 else None]
        if re.search(rf"\b{match.group(1)}\b", rhs):
            diags.append(
                Diagnostic(
                    "warning",
                    path,
                    line_of(masked, match.start()),
                    f'Combinational self-reference on "{match.group(1)}".',
                    "A continuous assignment that reads its own net is a combinational loop.",
                    "Break the loop with a register or remove the self-reference.",
                    "combo-loop",
                )
            )
        if match.group(1) not in declared and match.group(1) not in ports:
            diags.append(
                Diagnostic(
                    "warning",
                    path,
                    line_of(masked, match.start()),
                    f'Implicit net "{match.group(1)}".',
                    "An undeclared assign target becomes a 1-bit wire and silently truncates the value.",
                    f'Declare "{match.group(1)}" with an explicit width before the assignment.',
                    "implicit",
                )
            )
    for name, lines in drivers.items():
        unique_regions = sorted(set(lines))
        if len(unique_regions) > 1 and name not in {"state"}:
            diags.append(
                Diagnostic(
                    "warning",
                    path,
                    unique_regions[1],
                    f'Multiple drivers on "{name}".',
                    "Two processes writing one signal fight in simulation and are illegal in synthesis.",
                    f"Drive \"{name}\" from a single process.",
                    "multidriver",
                )
            )
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*(?:<=|=)(?!=)\s*([A-Za-z_]\w*)\b(?!\s*\[)", masked):
        lhs, rhs = match.group(1), match.group(2)
        if lhs not in declared or rhs not in declared:
            continue
        lw, rw = declared[lhs][1], declared[rhs][1]
        if lw and rw and lw != rw:
            diags.append(
                Diagnostic(
                    "warning",
                    path,
                    line_of(masked, match.start()),
                    f'Width mismatch: "{lhs}" is {lw} bits and "{rhs}" is {rw} bits.',
                    "The narrower value is zero-extended or truncated, which changes arithmetic results.",
                    "Match the widths, or add an explicit cast that documents the truncation.",
                    "width",
                )
            )
        if declared[lhs][2] != declared[rhs][2]:
            diags.append(
                Diagnostic(
                    "info",
                    path,
                    line_of(masked, match.start()),
                    f'Signedness differs between "{lhs}" and "{rhs}".',
                    "Signed and unsigned operands use different rules for extension.",
                    "Cast both sides to the same signedness.",
                    "signed",
                )
            )
    uses = {name: len(re.findall(rf"\b{name}\b", masked)) for name in declared}
    for name, count in uses.items():
        if name in ports or count > 1:
            continue
        diags.append(
            Diagnostic(
                "warning",
                path,
                declared[name][0],
                f'Unused signal "{name}".',
                "An unused declaration usually means a connection was forgotten or logic was deleted.",
                f'Remove "{name}", or drive and read it.',
                "unused",
            )
        )
    return diags


def summarize(diags: list[Diagnostic]) -> dict:
    errors = sum(1 for d in diags if d.severity == "error")
    warnings = sum(1 for d in diags if d.severity == "warning")
    infos = sum(1 for d in diags if d.severity == "info")
    penalty = errors * 25 + warnings * 8 + infos * 1
    score = max(0, 100 - penalty)
    return {
        "errors": errors,
        "warnings": warnings,
        "info": infos,
        "synthesizability": score,
        "diagnostics": [d.as_dict() for d in diags],
    }

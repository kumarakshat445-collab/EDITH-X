"""Task router. Deterministic tools run first. The rule engine only writes prose from tool output."""

from __future__ import annotations

import re

from .analyzer import analyze_source
from .debug import explain_diff, propose
from .generate import generate_rtl, generate_testbench
from .pipeline import load_sim_log
from .projects import design_sources, safe_project
from .settings import Settings
from .sv import mask_comments, parse_modules


def route(message: str) -> str:
    text = message.lower()
    if "assert" in text:
        return "assertions"
    if "testbench" in text or re.search(r"\btb\b", text):
        if any(word in text for word in ("generate", "write", "create", "build")):
            return "testbench"
    if any(word in text for word in ("generate", "create", "write", "build")) and any(
        word in text for word in ("rtl", "module", "fifo", "counter", "alu", "uart", "mux", "shift", "verilog")
    ):
        return "generate"
    if any(word in text for word in ("static", "synthes", "latch", "lint", "unused", "diagnostic")):
        return "analyze"
    if any(word in text for word in ("fail", "debug", "root cause", "mismatch", "why does", "testbench fail")):
        return "debug"
    if "optimi" in text or "area" in text:
        return "optimize"
    if "race" in text:
        return "race"
    if "convert" in text:
        return "convert"
    if "random" in text:
        return "random"
    if "waveform" in text:
        return "waveform"
    if text.startswith("fix") or " fix " in f" {text} ":
        return "fix"
    return "explain"


def answer(project_id: str, message: str, active_file: str | None, selection: str | None, mode: str, settings: Settings) -> dict:
    project = safe_project(project_id)
    if not project.is_dir():
        raise FileNotFoundError("Project was not found.")
    files = design_sources(project)
    task = route(message)
    backend = "rule-engine"
    code = None
    suggested_path = None
    proposal = None

    if task == "generate":
        generated = generate_rtl(message)
        text = _generation_text(generated)
        if generated.files:
            code = generated.files[0].content
            suggested_path = generated.files[0].path
        return _pack(task, backend, text, code, suggested_path, proposal, generated.as_dict())

    if task == "testbench":
        generated = generate_testbench(files, active_file)
        text = _generation_text(generated)
        if generated.files:
            code = generated.files[0].content
            suggested_path = generated.files[0].path
        return _pack(task, backend, text, code, suggested_path, proposal)

    full_source, path = _focus(files, active_file, None)
    source = selection.strip() if selection and selection.strip() else full_source
    if task == "analyze":
        text = _analyze_text(files, path, mode)
    elif task in {"debug", "fix"}:
        log = load_sim_log(project_id)
        found = propose(files, log, mode)
        proposal = found.as_dict()
        text = _proposal_text(found, mode)
    elif task == "assertions":
        text, code, suggested_path = _assertions(full_source, path, mode)
    elif task == "optimize":
        text = _optimize(files, path, mode)
    elif task == "race":
        text = _races(full_source, path, mode)
    elif task == "convert":
        text, code, proposal = _convert(full_source, path)
    elif task == "random":
        text, code, suggested_path = _random(source, path)
    elif task == "waveform":
        text = _waveform(project_id, mode)
    else:
        text = _explain(source, path, selection, mode)
    return _pack(task, backend, text, code, suggested_path, proposal)


def _pack(task, backend, text, code, suggested_path, proposal, extra=None) -> dict:
    return {
        "route": task,
        "backend": backend,
        "text": text,
        "code": code,
        "suggested_path": suggested_path,
        "proposal": proposal,
        "extra": extra,
    }


def _focus(files: dict[str, str], active: str | None, selection: str | None) -> tuple[str, str]:
    if active and active in files:
        if selection and selection.strip():
            return selection, active
        return files[active], active
    for path, src in files.items():
        if path.startswith("rtl/"):
            return src, path
    if files:
        path = next(iter(files))
        return files[path], path
    return "", ""


def _generation_text(generated) -> str:
    if not generated.ok:
        return generated.message
    assumptions = "\n".join(f"- {item}" for item in generated.assumptions)
    interface = "\n".join(f"- {item}" for item in generated.interface)
    files = "\n".join(f"- {item.path}" for item in generated.files)
    return (
        f"{generated.message}\n\nAssumptions\n{assumptions}\n\nInterface\n{interface}\n\nFiles\n{files}\n\n"
        "The source below is template output from the rule engine. Run static analysis and simulation before you trust it."
    )


def _analyze_text(files: dict[str, str], focus: str, mode: str) -> str:
    chunks = []
    targets = {focus: files[focus]} if focus in files else {p: s for p, s in files.items() if p.startswith("rtl/")}
    for path, src in targets.items():
        diags = analyze_source(path, src)
        if not diags:
            chunks.append(f"{path}: no static findings.")
            continue
        for diag in diags:
            block = f"{diag.severity.upper()} {path}:{diag.line}\n{diag.problem}\nWhy: {diag.why}\nFix: {diag.fix}"
            if mode == "beginner":
                block += "\nThis came from the rule engine, not from a language model."
            chunks.append(block)
    return "\n\n".join(chunks) or "No RTL files are open."


def _proposal_text(found, mode: str) -> str:
    evidence = "\n".join(f"- {item}" for item in found.evidence)
    text = (
        f"Root cause\n{found.root_cause}\n\nEvidence\n{evidence}\n\n"
        f"Proposed fix\n{found.proposed_fix}\n\nWhy the fix works\n{found.why}"
    )
    if mode == "professional":
        return text
    return text + "\n\nThe file is unchanged until you apply the diff."


def _explain(source: str, path: str, selection: str | None, mode: str) -> str:
    if not source:
        return "Open an RTL file first. The copilot reads the active buffer and does not use a cloud model."
    modules = parse_modules(source if not selection else source)
    if selection and selection.strip() and path:
        # Selection may be a fragment. Explain that fragment plus any module we could parse from the full file.
        body = selection.strip()
    else:
        body = source
    lines = [f"File: {path or 'selection'}", f"Backend: rule engine. No model weights were executed."]
    parsed = parse_modules(body) or modules
    if parsed:
        for module in parsed:
            ports = ", ".join(f"{p.direction} {p.name}" for p in module.ports) or "none parsed"
            params = ", ".join(f"{n}={v}" for n, v in module.parameters) or "none"
            lines.append(f"Module {module.name} (lines {module.start}-{module.end}).")
            lines.append(f"Parameters: {params}.")
            lines.append(f"Ports: {ports}.")
    always = re.findall(r"always_(?:ff|comb|latch)[^\n]*", mask_comments(body))
    if always:
        lines.append("Sequential/combinational procedures:")
        lines.extend(f"- {item.strip()}" for item in always[:8])
    if mode == "beginner":
        if "always_ff" in body:
            lines.append("always_ff means the process is intended to be flip-flops. Assignments should use <= so every flop updates on the clock edge.")
        if "always_comb" in body:
            lines.append("always_comb means pure combo logic. Every output of the process needs a value on every path, or synthesis infers a latch.")
    elif mode == "professional":
        lines.append("Ask for static analysis or a testbench when you want a check rather than a description.")
    if not parsed and not always:
        lines.append("No complete module header was found in the selection. Showing the selected text is intentional; nothing was inferred beyond it.")
        lines.append(body[:800])
    return "\n".join(lines)


def _assertions(source: str, path: str, mode: str) -> tuple[str, str | None, str | None]:
    modules = parse_modules(source)
    if not modules:
        return "Parse a module before asking for assertions.", None, None
    module = modules[0]
    clocks = [p.name for p in module.ports if p.name.lower() in {"clk", "clock"}]
    resets = [p.name for p in module.ports if "rst" in p.name.lower() or "reset" in p.name.lower()]
    clk = clocks[0] if clocks else None
    rst = resets[0] if resets else None
    lines = ["// Concurrent SVA. Icarus Verilog does not execute these. They are not counted as passing checks."]
    if clk:
        disable = f" disable iff ({rst})" if rst else ""
        lines.append(f"default clocking cb @(posedge {clk}); endclocking")
        for port in module.ports:
            if port.direction == "input":
                continue
            lines.append(f"assert property (@(posedge {clk}){disable} !$isunknown({port.name}));")
    else:
        for port in module.ports:
            if port.direction != "input":
                lines.append(f"assert (!$isunknown({port.name}));")
    code = "\n".join(lines) + "\n"
    note = "These assertions only say outputs are not X. They do not invent a protocol."
    if mode == "beginner":
        note += " A property that passes on Icarus must be written as a procedural if in the testbench. Use Generate Testbench for checks this environment can run."
    return note + "\n\n" + code, code, f"tb/{module.name}_sva.sv"


def _optimize(files: dict[str, str], path: str, mode: str) -> str:
    src = files.get(path, "")
    diags = analyze_source(path, src) if src else []
    interesting = [d for d in diags if d.rule in {"latch", "delay", "initial", "blocking-seq", "nba-comb", "combo-loop"}]
    if not interesting:
        return (
            f"{path or 'RTL'}: the rule engine found no latch, delay, or assignment-style issue that would change area. "
            "A cell-count comparison needs Yosys, which VERIFY RTL already runs. No area number is invented here."
        )
    lines = ["Area-related findings:"]
    for diag in interesting:
        lines.append(f"- {path}:{diag.line} {diag.problem} {diag.fix}")
    if mode == "beginner":
        lines.append("Latches and delay controls usually cost more control logic than a straightforward flop.")
    return "\n".join(lines)


def _races(source: str, path: str, mode: str) -> str:
    masked = mask_comments(source)
    hits = []
    for match in re.finditer(r"always_ff[^\n]*|always\s*@\s*\([^)]*edge[^)]*\)", masked):
        start = match.end()
        end = masked.find("end", start)
        body = masked[start:end if end != -1 else start + 200]
        for line in body.splitlines():
            if re.search(r"\b[A-Za-z_]\w*\s*=(?!=)", line) and "<=" not in line and not line.strip().startswith("for"):
                hits.append(line.strip())
    if not hits:
        return f"No blocking assignment was found in a clocked process in {path or 'the selection'}. That does not prove the design is race-free across modules."
    extra = " Blocking assignments update immediately, so another process can observe a half-updated cycle." if mode != "professional" else ""
    return "Possible intra-process race pattern:" + extra + "\n" + "\n".join(f"- {hit}" for hit in hits[:12])


def _convert(source: str, path: str) -> tuple[str, str | None, dict | None]:
    if not source.strip():
        return "Nothing is selected to convert.", None, None
    updated = source
    updated = re.sub(r"\breg\b", "logic", updated)
    updated = re.sub(r"\bwire\b", "logic", updated)
    updated = re.sub(r"\balways\s*@\s*\(\s*posedge\b", "always_ff @(posedge", updated)
    updated = re.sub(r"\balways\s*@\s*\(\s*\*\s*\)", "always_comb", updated)
    updated = re.sub(r"\balways\s*@\*", "always_comb", updated)
    if updated == source:
        return "No reg/wire or old always header was found to convert.", source, None
    from .debug import Proposal

    diff = __import__("difflib").unified_diff(
        source.splitlines(), updated.splitlines(), fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
    )
    proposal = Proposal(
        root_cause="Verilog constructs with SystemVerilog equivalents were found.",
        evidence=["reg/wire and always @(posedge/*) substitutions are textual."],
        proposed_fix="Replace reg and wire with logic, and use always_ff / always_comb.",
        why="The edit is a keyword substitution. Widths and behavior are otherwise unchanged.",
        diff="\n".join(diff),
        path=path,
        updated=updated if path else None,
        rule="sv-convert",
    )
    return "Keyword conversion only. Review the diff before applying. Ports that were split across Verilog-95 declarations are not rewritten.", updated, proposal.as_dict()


def _random(source: str, path: str) -> tuple[str, str | None, str | None]:
    modules = parse_modules(source)
    if not modules:
        return "A module parse is required before a random test can be built.", None, None
    module = modules[0]
    clk = next((p.name for p in module.ports if p.name.lower() in {"clk", "clock"}), None)
    inputs = [p for p in module.ports if p.direction == "input" and p.name != clk]
    body = [f"// Constrained-random style stimulus using $urandom. Icarus does not implement std::randomize."]
    body.append("initial begin")
    body.append("    repeat (20) begin")
    if clk:
        body.append(f"        @(posedge {clk});")
    for port in inputs:
        if "rst" in port.name.lower() or "reset" in port.name.lower():
            body.append(f"        {port.name} = 1'b0;")
        else:
            body.append(f"        {port.name} = $urandom;")
    body.append("    end")
    body.append("end")
    code = "\n".join(body) + "\n"
    return (
        "This is a stimulus fragment, not a self-checking test. Seed and constraints are the literal $urandom calls below. "
        "It does not claim functional coverage.",
        code,
        f"tb/{module.name}_random.sv",
    )


def _waveform(project_id: str, mode: str) -> str:
    log = load_sim_log(project_id)
    fails = [line for line in log.splitlines() if line.startswith("FAIL ")]
    if not fails:
        return "No failing check is in the last simulation log. The waveform panel shows dump.vcd after a simulation that called $dumpvars."
    shown = "\n".join(fails[:10])
    extra = " Compare the expected and got values against the data signal in the waveform tab." if mode != "professional" else ""
    return f"The last simulation failed these checks:{extra}\n{shown}\n\nOpen the Waveform tab for dump.vcd. The rule engine does not invent transition times."


def explain_change(diff: str, mode: str) -> str:
    return explain_diff(diff, mode)

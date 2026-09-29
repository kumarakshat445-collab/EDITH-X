"""Compile, simulate, synthesize, and the verification pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .analyzer import Diagnostic, analyze_source, summarize
from .debug import propose
from .generate import generate_testbench
from .projects import design_sources, safe_project
from .settings import Settings
from .sv import parse_modules
from .tools import ToolError, parse_result, run_argv, tool_status, which
from .vcd import parse_vcd


def _project(project_id: str) -> Path:
    path = safe_project(project_id)
    if not path.is_dir():
        raise FileNotFoundError("Project was not found.")
    return path


def analyze_project(project_id: str, settings: Settings, focus: str | None = None) -> dict:
    project = _project(project_id)
    files = design_sources(project)
    if focus:
        files = {k: v for k, v in files.items() if k == focus}
        if not files:
            raise FileNotFoundError("File was not found.")
    diags: list[Diagnostic] = []
    modules = []
    for path, src in sorted(files.items()):
        modules.extend({"name": m.name, "file": path, "ports": [p.name for p in m.ports]} for m in parse_modules(src))
        diags.extend(analyze_source(path, src))
    diags.extend(_verilator_lint(project, files, settings))
    summary = summarize(diags)
    summary["modules"] = modules
    _write_json(project / ".hexa" / "diagnostics.json", summary)
    return summary


def _verilator_lint(project: Path, files: dict[str, str], settings: Settings) -> list[Diagnostic]:
    binary = which(settings, "verilator", settings.verilator_path)
    sources = [project / path for path in files if path.startswith("rtl/") and path.endswith((".sv", ".v"))]
    if not binary or not sources:
        return []
    proc = run_argv(
        [binary, "--lint-only", "-sv", "-Wno-WIDTHEXPAND", "-Wno-MULTITOP", "-Wno-UNUSEDSIGNAL", *[str(p) for p in sources]],
        project,
        timeout=40,
    )
    diags: list[Diagnostic] = []
    for line in (proc.stderr + proc.stdout).splitlines():
        if not line.startswith("%"):
            continue
        if "WIDTHEXPAND" in line or "MULTITOP" in line:
            continue
        severity = "error" if line.startswith("%Error") else "warning" if line.startswith("%Warning") else "info"
        # %Warning-CASEINCOMPLETE: file:line:col: message
        body = line.split(":", 1)[-1] if ":" in line else line
        file = ""
        lineno = 1
        message = line
        parts = line.split(":", 4)
        if len(parts) >= 4 and parts[1].strip().endswith((".sv", ".v")):
            # token may be "%Warning-FOO"
            pass
        import re

        match = re.search(r"((?:rtl|tb)/[^\s:]+\.(?:sv|v)):(\d+):\s*(.*)", line)
        if match:
            file, lineno, message = match.group(1), int(match.group(2)), match.group(3)
        else:
            continue
        diags.append(
            Diagnostic(
                severity if severity != "info" else "info",
                file,
                lineno,
                message.strip() or body.strip(),
                "Reported by Verilator lint. HEXA-R did not rewrite this message.",
                "Inspect the cited line. Verilator's manual documents the warning code.",
                "verilator",
            )
        )
    return diags


def ensure_testbench(project_id: str, focus: str | None = None) -> dict:
    project = _project(project_id)
    files = design_sources(project)
    existing = [path for path in files if path.startswith("tb/") and path.endswith(("_tb.sv", "_tb.v"))]
    if existing and focus is None:
        return {"written": False, "path": existing[0], "message": "A testbench is already in the project."}
    generated = generate_testbench(files, focus)
    if not generated.ok:
        return generated.as_dict()
    for item in generated.files:
        target = project / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")
    payload = generated.as_dict()
    payload["written"] = True
    payload["path"] = generated.files[0].path if generated.files else None
    return payload


def compile_project(project_id: str, settings: Settings) -> dict:
    project = _project(project_id)
    tools = tool_status(settings)
    if not tools["icarus"]["detected"]:
        return {"ok": False, "stage": "compile", "log": tools["icarus"]["hint"], "tool": None}
    files = design_sources(project)
    sources = [project / path for path in sorted(files) if path.endswith((".sv", ".v"))]
    if not sources:
        return {"ok": False, "stage": "compile", "log": "The project has no Verilog sources.", "tool": "iverilog"}
    top = _top_name(files)
    out = project / ".hexa"
    out.mkdir(parents=True, exist_ok=True)
    binary = project / ".hexa" / "sim.vvp"
    args = [tools["icarus"]["path"], "-g2012", "-o", str(binary)]
    if top:
        args.extend(["-s", top])
    args.extend(str(path) for path in sources)
    proc = run_argv(args, project, timeout=30)
    log = (proc.stdout + proc.stderr).strip()
    (out / "compile.log").write_text(log, encoding="utf-8")
    return {
        "ok": proc.returncode == 0 and binary.is_file(),
        "stage": "compile",
        "tool": tools["icarus"]["path"],
        "top": top,
        "exit_code": proc.returncode,
        "log": log or ("Compiled " + ", ".join(path.name for path in sources)),
    }


def simulate_project(project_id: str, settings: Settings) -> dict:
    compiled = compile_project(project_id, settings)
    if not compiled["ok"]:
        return {
            "ok": False,
            "stage": "simulate",
            "compile": compiled,
            "log": compiled["log"],
            "result": parse_result(compiled["log"]),
            "waveform": False,
        }
    project = _project(project_id)
    vvp = which(settings, "vvp", "")
    if not vvp:
        return {"ok": False, "stage": "simulate", "log": "vvp was not detected next to iverilog.", "compile": compiled, "result": parse_result(""), "waveform": False}
    run_dir = project / ".hexa"
    proc = run_argv([vvp, str(run_dir / "sim.vvp")], run_dir, timeout=30)
    log = (proc.stdout + proc.stderr).strip()
    (run_dir / "sim.log").write_text(log, encoding="utf-8")
    result = parse_result(log)
    waveform = (run_dir / "dump.vcd").is_file()
    ok = proc.returncode == 0 and result["verdict"] == "PASSED"
    return {"ok": ok, "stage": "simulate", "exit_code": proc.returncode, "log": log, "result": result, "compile": compiled, "waveform": waveform}


def synth_project(project_id: str, settings: Settings) -> dict:
    project = _project(project_id)
    tools = tool_status(settings)
    if not tools["yosys"]["detected"]:
        return {"ok": False, "log": tools["yosys"]["hint"], "tool": None}
    files = design_sources(project)
    rtl = [str(project / path) for path in sorted(files) if path.startswith("rtl/") and path.endswith((".sv", ".v"))]
    if not rtl:
        return {"ok": False, "log": "No RTL files to synthesize.", "tool": "yosys"}
    top = _design_top(files)
    script = "read_verilog -sv " + " ".join(rtl) + f"; synth -top {top}; stat"
    proc = run_argv([tools["yosys"]["path"], "-p", script], project, timeout=40)
    log = (proc.stdout + proc.stderr).strip()
    (project / ".hexa").mkdir(exist_ok=True)
    (project / ".hexa" / "yosys.log").write_text(log, encoding="utf-8")
    cells = None
    for line in log.splitlines():
        if "Number of cells:" in line:
            cells = line.split(":")[-1].strip()
    return {"ok": proc.returncode == 0, "log": log[-4000:], "cells": cells, "top": top, "tool": tools["yosys"]["path"]}


def verify_project(project_id: str, settings: Settings, mode: str) -> dict:
    project = _project(project_id)
    steps = []
    files = design_sources(project)
    modules = []
    parse_ok = True
    parse_error = ""
    for path, src in sorted(files.items()):
        if "/tb/" in f"/{path}" or not path.endswith((".sv", ".v")):
            continue
        try:
            found = parse_modules(src)
            if "module" in src and not found:
                parse_ok = False
                parse_error = f"{path}: module header was not parsed."
            modules.extend(m.name for m in found)
        except ValueError as exc:
            parse_ok = False
            parse_error = f"{path}: {exc}"
    steps.append({"id": "parse", "label": "Parse", "status": "pass" if parse_ok and modules else "fail", "detail": parse_error or f"{len(modules)} module(s): {', '.join(modules)}"})

    analysis = analyze_project(project_id, settings)
    static_status = "fail" if analysis["errors"] else "warn" if analysis["warnings"] else "pass"
    steps.append({
        "id": "static",
        "label": "Static Analysis",
        "status": static_status,
        "detail": f"{analysis['errors']} errors, {analysis['warnings']} warnings",
        "diagnostics": analysis["diagnostics"],
    })

    tb_paths = [path for path in files if path.startswith("tb/") and path.endswith(("_tb.sv", "_tb.v"))]
    if not tb_paths:
        generated = ensure_testbench(project_id)
        tb_status = "pass" if generated.get("written") or generated.get("ok") else "fail"
        tb_detail = generated.get("message") or generated.get("path") or "Testbench was not created."
        tb_path = generated.get("path")
    else:
        tb_status = "pass"
        tb_detail = tb_paths[0]
        tb_path = tb_paths[0]
    steps.append({"id": "testbench", "label": "Testbench", "status": tb_status, "detail": tb_detail, "path": tb_path})

    compiled = compile_project(project_id, settings)
    steps.append({"id": "compile", "label": "Compile", "status": "pass" if compiled["ok"] else "fail", "detail": compiled.get("top") or "", "log": compiled.get("log", "")})

    sim = {"ok": False, "log": "Simulation did not run.", "result": parse_result(""), "waveform": False}
    if compiled["ok"] and tb_status != "fail":
        sim = simulate_project(project_id, settings)
    sim_status = "pass" if sim.get("ok") else "fail"
    result = sim.get("result") or parse_result("")
    steps.append({
        "id": "simulate",
        "label": "Simulation",
        "status": sim_status,
        "detail": _result_text(result),
        "log": sim.get("log", ""),
        "waveform": sim.get("waveform", False),
    })
    checks_status = "pass" if result.get("verdict") == "PASSED" else "fail" if result.get("tests") else "skip"
    steps.append({
        "id": "assertions",
        "label": "Assertions",
        "status": checks_status,
        "detail": "Procedural checks from the testbench. Concurrent SVA was not executed.",
        "passed": result.get("passed"),
        "failed": result.get("failed"),
    })

    synth = synth_project(project_id, settings)
    log_for_ai = sim.get("log") or compiled.get("log") or ""
    fresh = design_sources(project)
    proposal = propose(fresh, log_for_ai, mode) if not sim.get("ok") else propose(fresh, "", mode)
    if sim.get("ok"):
        proposal_dict = {
            "root_cause": "Simulation passed. The rule engine has no failing check to explain.",
            "evidence": [line for line in (sim.get("log") or "").splitlines() if line.startswith("PASS ") or line.startswith("RESULT")],
            "proposed_fix": "No edit proposed.",
            "why": "The design matched the testbench contract on this run.",
            "diff": "",
            "path": None,
            "updated": None,
            "rule": "pass",
            "backend": "rule-engine",
            "can_apply": False,
        }
        ai_status = "pass"
    else:
        proposal_dict = proposal.as_dict()
        ai_status = "warn" if proposal_dict.get("can_apply") else "fail"
    steps.append({
        "id": "ai",
        "label": "AI Analysis",
        "status": ai_status,
        "detail": proposal_dict["rule"],
        "analysis": proposal_dict,
    })

    report = {
        "project": json.loads((project / "project.json").read_text(encoding="utf-8")).get("name", project_id) if (project / "project.json").is_file() else project_id,
        "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "errors": analysis["errors"],
        "warnings": analysis["warnings"],
        "synthesizability": analysis["synthesizability"],
        "compilation": "PASS" if compiled["ok"] else "FAIL",
        "simulation": "PASS" if sim.get("ok") else "FAIL",
        "tests": result.get("tests"),
        "passed": result.get("passed"),
        "failed": result.get("failed"),
        "assertions_passed": result.get("passed"),
        "assertions_failed": result.get("failed"),
        "assertions_note": "Counts are procedural testbench checks. Concurrent SVA was not run.",
        "synthesis": "PASS" if synth.get("ok") else "FAIL",
        "synthesis_cells": synth.get("cells"),
        "synthesis_log": synth.get("log"),
        "ai_rule": proposal_dict.get("rule"),
        "ai_summary": proposal_dict.get("root_cause"),
        "backend": "rule-engine",
        "steps": [{k: v for k, v in step.items() if k != "diagnostics"} for step in steps],
    }
    reports = project / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (reports / "verification.md").write_text(_markdown(report), encoding="utf-8")
    return {"ok": bool(sim.get("ok")) and compiled["ok"] and analysis["errors"] == 0, "steps": steps, "report": report, "proposal": proposal_dict}


def waveform(project_id: str) -> dict:
    project = _project(project_id)
    return parse_vcd(project / ".hexa" / "dump.vcd")


def read_report(project_id: str) -> dict:
    project = _project(project_id)
    path = project / "reports" / "verification.json"
    if not path.is_file():
        return {"available": False, "markdown": "No verification report yet. Run VERIFY RTL."}
    data = json.loads(path.read_text(encoding="utf-8"))
    md = (project / "reports" / "verification.md").read_text(encoding="utf-8")
    return {"available": True, "report": data, "markdown": md}


def _top_name(files: dict[str, str]) -> str | None:
    tb = []
    for path, src in files.items():
        if "/tb/" not in f"/{path}" and not path.endswith("_tb.sv"):
            continue
        tb.extend(m.name for m in parse_modules(src))
    return tb[0] if tb else _design_top(files)


def _design_top(files: dict[str, str]) -> str:
    names = []
    for path, src in files.items():
        if not path.startswith("rtl/"):
            continue
        names.extend(m.name for m in parse_modules(src))
    for prefer in ("uart_top", "counter", "sync_fifo", "alu"):
        if prefer in names:
            return prefer
    return names[0] if names else "top"


def _result_text(result: dict) -> str:
    if result.get("tests") is None:
        return result.get("verdict") or "No RESULT line."
    return f"{result['passed']}/{result['tests']} passed, verdict {result['verdict']}"


def _markdown(report: dict) -> str:
    tests = report.get("tests")
    test_line = "not run" if tests is None else f"{tests} total\n{report.get('passed')} passed\n{report.get('failed')} failed"
    return f'''RTL VERIFICATION REPORT

Project: {report["project"]}
Generated: {report["generated_at"]}
Backend: {report["backend"]}

Static Analysis
----------------
Errors: {report["errors"]}
Warnings: {report["warnings"]}
Synthesizability score: {report["synthesizability"]}

Compilation
-----------
{report["compilation"]}

Simulation
----------
{report["simulation"]}

Tests
-----
{test_line}

Assertions
----------
{report.get("assertions_passed")} passed
{report.get("assertions_failed")} failed
{report["assertions_note"]}

Synthesizability
----------------
{report["synthesis"]}
Cells: {report.get("synthesis_cells") or "n/a"}

AI Review
---------
Rule: {report.get("ai_rule")}
{report.get("ai_summary")}
'''


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_sim_log(project_id: str) -> str:
    path = _project(project_id) / ".hexa" / "sim.log"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    compile_log = _project(project_id) / ".hexa" / "compile.log"
    return compile_log.read_text(encoding="utf-8") if compile_log.is_file() else ""

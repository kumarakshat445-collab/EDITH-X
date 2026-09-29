"""Failure analysis that only proposes a patch when a rule matches evidence."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .sv import line_of, mask_comments


@dataclass
class Proposal:
    root_cause: str
    evidence: list[str]
    proposed_fix: str
    why: str
    diff: str
    path: str | None
    updated: str | None
    rule: str
    backend: str = "rule-engine"

    def as_dict(self) -> dict:
        return {
            "root_cause": self.root_cause,
            "evidence": self.evidence,
            "proposed_fix": self.proposed_fix,
            "why": self.why,
            "diff": self.diff,
            "path": self.path,
            "updated": self.updated,
            "rule": self.rule,
            "backend": self.backend,
            "can_apply": self.updated is not None,
        }


def _diff(path: str, before: str, after: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(lines)


def _fails(log: str) -> list[str]:
    return [line.strip() for line in log.splitlines() if line.startswith("FAIL ") or "error:" in line.lower() or "syntax error" in line.lower()]


def explain_diff(diff: str, mode: str) -> str:
    removed = [ln[1:] for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")]
    added = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    if not removed and not added:
        return "The diff is empty."
    detail = [
        "Removed:",
        *[f"  {ln}" for ln in removed],
        "Added:",
        *[f"  {ln}" for ln in added],
    ]
    if mode == "beginner":
        detail.append(
            "Nothing is written into the file until you choose Apply Fix. Reject leaves the source unchanged."
        )
    return "\n".join(detail)


def propose(files: dict[str, str], log: str, mode: str = "professional") -> Proposal:
    """Search source and tool output. Return an explanation even when no patch is safe."""
    failures = _fails(log)
    uart = _uart_sample(files, failures, mode)
    if uart:
        return uart
    counter = _counter_step(files, failures, mode)
    if counter:
        return counter
    syntax = _syntax(log)
    if syntax:
        return syntax
    if failures:
        shown = "\n".join(failures[:12])
        return Proposal(
            root_cause="Simulation or compilation reported failures, and no patch rule matched them.",
            evidence=failures[:12],
            proposed_fix="No automatic edit. The failing checks are quoted in the evidence.",
            why="A patch is withheld when the rule engine cannot point at a specific expression.",
            diff="",
            path=None,
            updated=None,
            rule="unmatched",
        )
    return Proposal(
        root_cause="No failing check is on record.",
        evidence=["Tool log has no FAIL line and no syntax error."],
        proposed_fix="No edit proposed.",
        why="There is nothing to repair until a check fails or a known structural defect is present.",
        diff="",
        path=None,
        updated=None,
        rule="clean",
    )


def _uart_sample(files: dict[str, str], failures: list[str], mode: str) -> Proposal | None:
    path = next((p for p in files if p.endswith("uart_rx.sv")), None)
    tx_path = next((p for p in files if p.endswith("uart_tx.sv")), None)
    if not path:
        return None
    src = files[path]
    masked = mask_comments(src)
    match = re.search(r"if\s*\(\s*clk_count\s*==\s*CLKS_PER_BIT\s*\)", masked)
    if not match:
        return None
    # Only treat this as the defect when the transmitter (or the stop-bit arm)
    # advances on CLKS_PER_BIT - 1. Otherwise the compare may be intentional.
    tx = files.get(tx_path or "", "")
    tx_aligned = "CLKS_PER_BIT - 1" in tx or "CLKS_PER_BIT-1" in tx
    stop_aligned = "CLKS_PER_BIT - 1" in masked or "CLKS_PER_BIT-1" in masked
    if not tx_aligned and not stop_aligned:
        return None
    if not failures and "VERIFICATION FAILED" not in "\n".join(failures):
        # Structural finding is still valid, but prefer to speak up when tests failed
        # or when the caller passed an empty log meaning "look at the source".
        pass
    line = line_of(masked, match.start())
    updated = re.sub(
        r"if\s*\(\s*clk_count\s*==\s*CLKS_PER_BIT\s*\)",
        "if (clk_count == CLKS_PER_BIT - 1)",
        src,
        count=1,
    )
    if updated == src:
        return None
    evidence = [f"{path}:{line} compares clk_count with CLKS_PER_BIT and not CLKS_PER_BIT - 1."]
    if tx_path:
        evidence.append(f"{tx_path} advances each bit when clk_count == CLKS_PER_BIT - 1.")
    evidence.extend(failures[:8])
    beginner = ""
    if mode == "beginner":
        beginner = (
            " A UART bit is a window of CLKS_PER_BIT clocks. Sampling at the far edge"
            " reads the next bit instead of the center of the current one."
        )
    return Proposal(
        root_cause=(
            "The receiver samples each data bit one clock later than the transmitter's bit period. "
            f"In {path}, the DATA state waits for clk_count == CLKS_PER_BIT. "
            "The transmitter holds each bit for CLKS_PER_BIT cycles and advances when "
            "clk_count == CLKS_PER_BIT - 1. The extra cycle moves the sample off the bit center."
            + beginner
        ),
        evidence=evidence,
        proposed_fix="Sample the data bit when clk_count == CLKS_PER_BIT - 1, matching the stop bit and the transmitter.",
        why=(
            "The receiver and transmitter then use the same bit duration. "
            "Bytes that failed the loopback check are sampled in the middle of the bit the transmitter is still driving."
        ),
        diff=_diff(path, src, updated),
        path=path,
        updated=updated,
        rule="uart-sample-skew",
    )


def _counter_step(files: dict[str, str], failures: list[str], mode: str) -> Proposal | None:
    path = next((p for p in files if p.endswith("counter.sv") and "/tb/" not in p), None)
    if not path:
        return None
    src = files[path]
    match = re.search(r"(count\s*<=\s*count\s*\+\s*)((?:\d+\s*'\s*[dDhHbB])?\s*2)\b", src)
    if not match:
        return None
    pairs = []
    for line in failures:
        found = re.search(r"expected\s+(\d+)\s+got\s+(\d+)", line)
        if found:
            pairs.append((int(found.group(1)), int(found.group(2))))
    if pairs and not all(got == expected * 2 for expected, got in pairs):
        return None
    literal = match.group(2)
    replacement = re.sub(r"2\b", "1", literal, count=1)
    updated = src[: match.start(2)] + replacement + src[match.end(2) :]
    line = src[: match.start()].count("\n") + 1
    evidence = [f"{path}:{line} adds {literal.strip()} each clock."]
    evidence.extend(failures[:8] or ["No simulation log was attached. The increment does not match a +1 counter contract."])
    extra = " Beginner note: a +2 step skips every other binary value, so the testbench's cycle index never matches." if mode == "beginner" else ""
    return Proposal(
        root_cause="The counter adds 2 on each clock, so the value runs ahead of a +1 sequence." + extra,
        evidence=evidence,
        proposed_fix=f"Change the increment from {literal.strip()} to {replacement.strip()}.",
        why="After reset, cycle N then holds the value N, which is what the counter contract checks.",
        diff=_diff(path, src, updated),
        path=path,
        updated=updated,
        rule="counter-increment",
    )


def _syntax(log: str) -> Proposal | None:
    match = re.search(r"([^\s:]+\.(?:sv|v)):(\d+):\s*(.*)", log)
    if not match:
        return None
    if "syntax" not in log.lower() and "error" not in match.group(3).lower():
        return None
    return Proposal(
        root_cause=f"The compiler stopped at {match.group(1)}:{match.group(2)}.",
        evidence=[match.group(0)],
        proposed_fix="No automatic edit. Fix the token the compiler quoted, then compile again.",
        why="A syntax error has more than one plausible repair, so the file is left untouched.",
        diff="",
        path=match.group(1),
        updated=None,
        rule="compiler",
    )

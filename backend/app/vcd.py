"""Minimal VCD reader for the waveform panel. Unknown constructs are skipped."""

from __future__ import annotations

import re
from pathlib import Path


def parse_vcd(path: Path, limit_per_signal: int = 8000) -> dict:
    if not path.is_file():
        return {"available": False, "reason": "No waveform captured. Run simulation to generate a VCD."}
    text = path.read_text(encoding="utf-8", errors="replace")
    if "$enddefinitions" not in text:
        return {"available": False, "reason": "VCD file does not contain an enddefinitions marker."}
    header, _, body = text.partition("$enddefinitions")
    signals: dict[str, dict] = {}
    timescale = ""
    ts = re.search(r"\$timescale\s+(.+?)\$end", header, re.S)
    if ts:
        timescale = " ".join(ts.group(1).split())
    for match in re.finditer(r"\$var\s+\w+\s+(\d+)\s+(\S+)\s+([^\s$]+)", header):
        width = int(match.group(1))
        ident = match.group(2)
        name = match.group(3)
        signals[ident] = {"name": name, "width": width, "id": ident, "changes": []}
    time = 0
    truncated = False
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("$"):
            continue
        if line.startswith("#"):
            try:
                time = int(line[1:])
            except ValueError:
                continue
            continue
        if line[0] in "01xXzZ":
            ident = line[1:]
            value = line[0]
        elif line[0] in "bBrR":
            parts = line.split()
            if len(parts) != 2:
                continue
            value, ident = parts[0][1:], parts[1]
        else:
            continue
        sig = signals.get(ident)
        if not sig:
            continue
        changes: list = sig["changes"]
        if len(changes) >= limit_per_signal:
            truncated = True
            continue
        changes.append([time, value])
    ordered = sorted(signals.values(), key=lambda item: item["name"])
    end = 0
    for sig in ordered:
        if sig["changes"]:
            end = max(end, sig["changes"][-1][0])
    return {
        "available": True,
        "timescale": timescale,
        "end": end,
        "truncated": truncated,
        "signals": ordered,
    }

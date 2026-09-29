"""Local EDA tools. Commands are argv lists, never a shell string."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .settings import Settings


class ToolError(RuntimeError):
    pass


def which(settings: Settings, name: str, override: str) -> str | None:
    if override:
        path = Path(override)
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(name)


def tool_status(settings: Settings) -> dict:
    catalog = {
        "icarus": ("iverilog", settings.icarus_path, "Icarus Verilog was not detected. Install iverilog or set the executable path in Settings."),
        "verilator": ("verilator", settings.verilator_path, "Verilator was not detected. Install Verilator or set the executable path in Settings."),
        "yosys": ("yosys", settings.yosys_path, "Yosys was not detected. Install Yosys or set the executable path in Settings."),
    }
    found = {}
    for key, (binary, override, hint) in catalog.items():
        path = which(settings, binary, override)
        version = ""
        if path:
            version = _version(path, key)
        found[key] = {"detected": bool(path), "path": path, "version": version, "hint": None if path else hint}
    return found


def _version(path: str, key: str) -> str:
    flag = ["--version"] if key != "icarus" else ["-V"]
    try:
        proc = subprocess.run([path, *flag], capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    text = (proc.stdout or proc.stderr or "").strip().splitlines()
    return text[0][:180] if text else ""


def run_argv(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    if not args or any(not isinstance(part, str) for part in args):
        raise ToolError("Refusing an empty command.")
    try:
        return subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"{Path(args[0]).name} timed out after {timeout}s.") from exc
    except OSError as exc:
        raise ToolError(f"Could not start {args[0]}: {exc}") from exc


_ALLOWED = {"iverilog", "vvp", "verilator", "yosys"}


def run_user_command(command: str, project: Path, settings: Settings) -> dict:
    if any(token in command for token in (";", "|", "&", "`", "$(", "\n", ">", "<")):
        raise ToolError("Pipes, redirection, and command chaining are not allowed.")
    try:
        parts = command.split()
    except ValueError as exc:
        raise ToolError("Command could not be parsed.") from exc
    if not parts:
        raise ToolError("Command is empty.")
    binary = Path(parts[0]).name
    if binary not in _ALLOWED:
        raise ToolError(f"{binary} is not an allowed simulator command. Allowed: {', '.join(sorted(_ALLOWED))}.")
    mapping = {
        "iverilog": which(settings, "iverilog", settings.icarus_path),
        "vvp": which(settings, "vvp", ""),
        "verilator": which(settings, "verilator", settings.verilator_path),
        "yosys": which(settings, "yosys", settings.yosys_path),
    }
    resolved = mapping[binary]
    if not resolved:
        raise ToolError(f"{binary} was not detected.")
    safe_args = [resolved]
    for arg in parts[1:]:
        if arg.startswith("-"):
            if any(ch in arg for ch in (";", "|", "&", "`")):
                raise ToolError("Flag rejected.")
            safe_args.append(arg)
            continue
        candidate = (project / arg).resolve() if not Path(arg).is_absolute() else Path(arg).resolve()
        project_resolved = project.resolve()
        if candidate != project_resolved and project_resolved not in candidate.parents:
            raise ToolError(f"{arg} is outside the project workspace.")
        if not candidate.exists():
            raise ToolError(f"{arg} does not exist in the project.")
        safe_args.append(str(candidate))
    proc = run_argv(safe_args, project, timeout=40)
    return {
        "argv": [binary, *parts[1:]],
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def parse_result(log: str) -> dict:
    match = re.search(r"RESULT tests=(\d+) passed=(\d+) failed=(\d+)", log)
    verdict = "PASSED" if "VERIFICATION PASSED" in log else "FAILED" if "VERIFICATION FAILED" in log else "UNKNOWN"
    if not match:
        return {"tests": None, "passed": None, "failed": None, "verdict": verdict}
    return {
        "tests": int(match.group(1)),
        "passed": int(match.group(2)),
        "failed": int(match.group(3)),
        "verdict": verdict,
    }

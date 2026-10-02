"""Environment fingerprint recorded with every run (R1).

A result is only comparable to another taken on the same fingerprint (same kernel, Python,
SQLite, sandbox tool and package versions, same code commit). Phase 9/M4 aborts on mismatch.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]


def _cmd(args: list[str]) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10, cwd=_ROOT)
        return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


def _version(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return ""


def fingerprint() -> dict[str, Any]:
    mem_kb = 0
    try:
        with open("/proc/meminfo") as f:
            mem_kb = int(next(line for line in f if line.startswith("MemTotal")).split()[1])
    except (OSError, StopIteration, ValueError):
        pass
    fp: dict[str, Any] = {
        "kernel": platform.release(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_gb": round(mem_kb / 1024 / 1024, 1),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "bwrap": _cmd(["bwrap", "--version"]),
        "packages": {p: _version(p) for p in ("pydantic", "httpx", "pyyaml")},
        "git_commit": _cmd(["git", "rev-parse", "HEAD"]),
        "git_dirty": bool(_cmd(["git", "status", "--porcelain", "--untracked-files=no"])),
    }
    fp["sha256"] = hashlib.sha256(json.dumps(
        {k: v for k, v in fp.items() if k not in ("git_commit", "git_dirty")},
        sort_keys=True).encode()).hexdigest()
    return fp

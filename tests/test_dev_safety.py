"""Phase 0 development-safety checks.

These inspect configuration only. They never open a protected path:
protected paths are passed to `git check-ignore` as strings, never read.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / ".claude" / "settings.json").read_text())
PROTECTED = [
    line.strip()
    for line in (ROOT / "configs" / "protected_paths.txt").read_text().splitlines()
    if line.strip() and not line.startswith("#")
]
DENY = set(SETTINGS["permissions"]["deny"])
SANDBOX = SETTINGS["sandbox"]

needs_git = pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(), reason="git repo required"
)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def test_protected_paths_listed():
    assert {".env", "secrets/", "benchmarks/held_out/"} <= set(PROTECTED)


@needs_git
@pytest.mark.parametrize("path", PROTECTED)
def test_protected_path_is_git_ignored(path):
    probe = path + "probe.txt" if path.endswith("/") else path
    assert _git("check-ignore", "-q", probe).returncode == 0, f"{path} not ignored"


@needs_git
@pytest.mark.parametrize("name", [".env.local", ".env.production", "secrets/k.json", "x.pem"])
def test_secret_variants_are_git_ignored(name):
    assert _git("check-ignore", "-q", name).returncode == 0


@needs_git
def test_env_example_is_not_ignored():
    assert _git("check-ignore", "-q", ".env.example").returncode != 0


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_path_denied_for_read_and_edit(path):
    rule = f"./{path}**" if path.endswith("/") else path
    assert f"Read({rule})" in DENY
    assert f"Edit({rule})" in DENY


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_path_denied_in_os_sandbox(path):
    assert SANDBOX["enabled"] is True
    assert f"./{path.rstrip('/')}" in SANDBOX["filesystem"]["denyRead"]


def test_env_example_not_blocked_by_wildcard():
    # Regression: Read(.env.*) + Read(!.env.example) made the sandbox deny .env.example
    # on Linux, because the negation is not carved out when globs are expanded.
    assert not any(r.startswith("Read(.env.*") or r.startswith("Read(!") for r in DENY)


def test_env_example_has_no_values_for_secrets():
    for line in (ROOT / ".env.example").read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if m and re.search(r"(KEY|TOKEN|SECRET)$", m.group(1)):
            assert m.group(2) == "", f"{m.group(1)} must be empty in .env.example"


def test_every_provider_key_is_unset_in_sandboxed_commands():
    names = {
        m.group(1)
        for line in (ROOT / ".env.example").read_text().splitlines()
        if (m := re.match(r"^([A-Z0-9_]+_API_KEY)=", line))
    }
    denied = {e["name"] for e in SANDBOX["credentials"]["envVars"] if e["mode"] == "deny"}
    assert names and names <= denied


@needs_git
def test_nothing_tracked_under_protected_paths():
    tracked = _git("ls-files").stdout.splitlines()
    assert tracked, "no tracked files: this check would pass vacuously"
    for path in PROTECTED:
        # Directory entries end with "/" and match by prefix; file entries match exactly
        # (a bare prefix would wrongly flag .env.example under ".env").
        hits = [t for t in tracked if (t.startswith(path) if path.endswith("/") else t == path)]
        assert not hits, path


# Patterns are split so this file does not match itself.
_SECRET_PATTERNS = [
    re.compile("sk-" + r"ant-[A-Za-z0-9_\-]{20,}"),
    re.compile("sk-" + r"(proj-)?[A-Za-z0-9]{32,}"),
    re.compile("AI" + r"za[0-9A-Za-z_\-]{35}"),
    re.compile("gh" + r"[pousr]_[A-Za-z0-9]{36}"),
    re.compile("-----BEGIN " + r"[A-Z ]*PRIVATE KEY-----"),
]


@needs_git
def test_no_secret_like_strings_in_tracked_files():
    hits = []
    tracked = _git("ls-files").stdout.splitlines()
    assert tracked, "no tracked files: this check would pass vacuously"
    for rel in tracked:
        p = ROOT / rel
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            continue
        hits += [f"{rel}: {pat.pattern[:12]}" for pat in _SECRET_PATTERNS if pat.search(text)]
    assert hits == []

"""Keep secrets out of logs, persisted records and child processes (PLAN 6.2).

Keys come from environment variables only. This module never stores or returns a secret
value: it redacts values, reports *names* of what it found, and builds child-process
environments from an allowlist instead of copying `os.environ`.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from typing import Any

# Same names the dev sandbox unsets (.claude/settings.json, sandbox.credentials.envVars).
SECRET_ENV_NAMES = frozenset({
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
})
# Any other variable whose name looks like a credential is treated as one too.
_SECRET_NAME_RE = re.compile(r"API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE_KEY", re.I)
# Shorter values are not used for redaction: replacing "a" everywhere would destroy text.
MIN_SECRET_LEN = 8

# Known key formats, caught even when the key is not in this process's environment.
# A pattern's `v` group, when present, is the part redacted (the prefix stays readable).
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")),
    ("sk_style_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+(?P<v>[A-Za-z0-9._~+/=\-]{12,})")),
    ("api_key_header", re.compile(
        r"(?i)\b(?:x-goog-api-key|x-api-key|api[_-]?key)[\"']?\s*[:=]\s*[\"']?"
        r"(?P<v>[A-Za-z0-9._~+/\-]{12,})")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

# Child processes get exactly these variables (plus allowlisted extras), never os.environ.
CHILD_ENV_BASE: dict[str, str] = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONIOENCODING": "utf-8",
}
CHILD_ENV_EXTRAS = frozenset({"HOME", "TMPDIR", "TZ", "LC_ALL", "PYTHONUNBUFFERED"})
CHILD_ENV_ALLOWED = frozenset(CHILD_ENV_BASE) | CHILD_ENV_EXTRAS


class SecretLeak(Exception):
    """Secret-like content was about to leave the process. The message holds names only."""


def is_secret_name(name: str) -> bool:
    return name.upper() in SECRET_ENV_NAMES or bool(_SECRET_NAME_RE.search(name))


def _env_secrets() -> list[tuple[str, str]]:
    found = [(n, v) for n, v in os.environ.items() if is_secret_name(n) and len(v) >= MIN_SECRET_LEN]
    return sorted(found, key=lambda nv: len(nv[1]), reverse=True)  # longest first: overlaps


def redact(text: str) -> str:
    for name, value in _env_secrets():
        text = text.replace(value, f"[REDACTED:{name}]")
    for name, pattern in _PATTERNS:
        def _sub(m: re.Match[str], name: str = name) -> str:
            if "v" in pattern.groupindex and m.group("v"):
                start, end = m.span("v")
                s0 = m.start()
                return m.group(0)[: start - s0] + f"[REDACTED:{name}]" + m.group(0)[end - s0:]
            return f"[REDACTED:{name}]"
        text = pattern.sub(_sub, text)
    return text


def find_secrets(text: str) -> list[str]:
    """Names (env var or pattern) of secrets present in `text`. Never the values."""
    names = [name for name, value in _env_secrets() if value in text]
    names += [name for name, pattern in _PATTERNS if pattern.search(text)]
    return names


def assert_no_secret(obj: Any, path: str = "$") -> None:
    """Raise SecretLeak if any string inside `obj` (keys included) holds a secret.

    Call before persisting anything (telemetry, SQLite, reports, memory).
    """
    if obj is None or isinstance(obj, (bool, int, float)):
        return
    if isinstance(obj, bytes):
        obj = obj.decode("utf-8", errors="replace")
    if isinstance(obj, str):
        names = find_secrets(obj)
        if names:
            raise SecretLeak(f"secret-like content ({', '.join(sorted(set(names)))}) at {path}")
        return
    if hasattr(obj, "model_dump"):  # pydantic models
        assert_no_secret(obj.model_dump(mode="json"), path)
        return
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            assert_no_secret(k, f"{path}.<key>")
            assert_no_secret(v, f"{path}.{k}" if isinstance(k, str) else f"{path}[?]")
        return
    if isinstance(obj, (list, tuple, set, frozenset)):
        for i, v in enumerate(obj):
            assert_no_secret(v, f"{path}[{i}]")
        return
    assert_no_secret(str(obj), path)


class RedactingFormatter(logging.Formatter):
    """Redacts the fully formatted line, so args and tracebacks are covered too."""

    def __init__(self, inner: logging.Formatter | None = None):
        super().__init__()
        self._inner = inner or logging.Formatter()

    def format(self, record: logging.LogRecord) -> str:
        return redact(self._inner.format(record))


def install_redaction(handler: logging.Handler) -> logging.Handler:
    """Wrap the handler's formatter. Call again if you later replace the formatter."""
    if not isinstance(handler.formatter, RedactingFormatter):
        handler.setFormatter(RedactingFormatter(handler.formatter))
    return handler


def child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Explicitly constructed environment for child processes (PLAN 6.2)."""
    env = dict(CHILD_ENV_BASE)
    for name, value in (extra or {}).items():
        if is_secret_name(name):
            raise SecretLeak(f"refusing secret-named variable {name} in child env")
        if find_secrets(value):
            raise SecretLeak(f"refusing secret-like value for {name} in child env")
        if name not in CHILD_ENV_EXTRAS:
            raise ValueError(f"variable {name} is not allowed in child env")
        env[name] = value
    return env

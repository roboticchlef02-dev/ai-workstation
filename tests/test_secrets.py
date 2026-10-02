"""M1 security tests: secrets never reach logs, persisted records or child processes.

Written before src/aiws/secretguard.py (CLAUDE.md: security tests first).
Fake key values are built at runtime so this file contains nothing that looks like a key.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys

import pytest

from aiws import secretguard as secrets
from aiws.secretguard import SecretLeak

FAKE_GEMINI = "AIza" + "Q" * 35
FAKE_ANTHROPIC = "sk-ant-api03-" + "a1B2" * 20
FAKE_GITHUB = "ghp_" + "Z" * 36
FAKE_CUSTOM = "plain-value-" + "9" * 20  # no known format: only caught via the env var name


@pytest.fixture
def fake_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_GEMINI)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    monkeypatch.setenv("MY_SERVICE_TOKEN", FAKE_CUSTOM)
    return [FAKE_GEMINI, FAKE_ANTHROPIC, FAKE_CUSTOM]


# --- redaction -------------------------------------------------------------------------

def test_redact_removes_values_of_secret_env_vars(fake_keys):
    text = f"a={FAKE_GEMINI} b={FAKE_ANTHROPIC} c={FAKE_CUSTOM}"
    out = secrets.redact(text)
    for v in fake_keys:
        assert v not in out
    assert "[REDACTED:GEMINI_API_KEY]" in out
    assert "[REDACTED:MY_SERVICE_TOKEN]" in out


@pytest.mark.parametrize("value", [FAKE_GEMINI, FAKE_ANTHROPIC, FAKE_GITHUB])
def test_redact_catches_known_formats_not_in_env(value, monkeypatch):
    for name in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    assert value not in secrets.redact(f"leaked: {value}.")


FAKE_TOKEN = "abcd" * 4 + "123"


@pytest.mark.parametrize("prefix", ["Authorization: Bearer ", "x-goog-api-key: ", "x-api-key: "])
def test_redact_catches_auth_headers(prefix):
    assert FAKE_TOKEN not in secrets.redact(prefix + FAKE_TOKEN)


def test_redact_leaves_ordinary_text_alone(fake_keys):
    text = "def solve(xs):\n    return sorted(xs)  # token count 42"
    assert secrets.redact(text) == text


def test_short_env_values_are_not_used_as_patterns(monkeypatch):
    # A 1-3 character "secret" would redact every occurrence of e.g. "a"; it is ignored instead.
    monkeypatch.setenv("SOME_API_KEY", "a")
    assert secrets.redact("banana") == "banana"


# --- scanning / persistence guard ------------------------------------------------------

def test_find_secrets_reports_names_never_values(fake_keys):
    found = secrets.find_secrets(f"x {FAKE_GEMINI} y {FAKE_GITHUB}")
    assert found
    joined = " ".join(found)
    assert FAKE_GEMINI not in joined and FAKE_GITHUB not in joined


def test_assert_no_secret_walks_nested_structures(fake_keys):
    record = {"run": 1, "calls": [{"prompt": "ok"}, {"meta": {"hdr": f"k={FAKE_ANTHROPIC}"}}]}
    with pytest.raises(SecretLeak) as exc:
        secrets.assert_no_secret(record)
    assert FAKE_ANTHROPIC not in str(exc.value)
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_assert_no_secret_checks_dict_keys(fake_keys):
    with pytest.raises(SecretLeak):
        secrets.assert_no_secret({FAKE_GEMINI: 1})


def test_assert_no_secret_accepts_clean_record(fake_keys):
    secrets.assert_no_secret({"model": "m", "tokens": [1, 2], "ok": True, "x": None, "f": 1.5})


# --- logging ---------------------------------------------------------------------------

def _capture(logger_name: str) -> tuple[logging.Logger, list[str]]:
    lines: list[str] = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            lines.append(self.format(record))

    log = logging.getLogger(logger_name)
    log.handlers[:] = []
    handler = ListHandler()
    secrets.install_redaction(handler)
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    log.propagate = False
    return log, lines


def test_log_redaction_covers_message_args_and_exceptions(fake_keys):
    log, lines = _capture("aiws.test.redaction")
    log.info("key=%s", FAKE_GEMINI)
    log.info(f"inline {FAKE_ANTHROPIC}")
    log.info("dict %s", {"k": FAKE_CUSTOM})
    try:
        raise RuntimeError(f"bad key {FAKE_GEMINI}")
    except RuntimeError:
        log.exception("failed")
    out = "\n".join(lines)
    assert len(lines) == 4
    for v in fake_keys:
        assert v not in out


# --- child process environment --------------------------------------------------------

def test_child_env_is_constructed_not_inherited(fake_keys, monkeypatch):
    monkeypatch.setenv("HOME", "/root")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    env = secrets.child_env()
    assert set(env) <= secrets.CHILD_ENV_ALLOWED
    for v in fake_keys:
        assert v not in json.dumps(env)
    assert "HTTPS_PROXY" not in env and "HOME" not in env


def test_child_env_rejects_secret_like_extras(fake_keys):
    with pytest.raises(SecretLeak):
        secrets.child_env({"OPENAI_API_KEY": "x" * 30})
    with pytest.raises(SecretLeak):
        secrets.child_env({"NOTE": FAKE_GEMINI})
    with pytest.raises(ValueError):
        secrets.child_env({"LD_PRELOAD": "/tmp/x.so"})


def test_real_subprocess_sees_only_the_constructed_env(fake_keys):
    code = "import json, os; print(json.dumps(dict(os.environ)))"
    out = subprocess.run(
        [sys.executable, "-c", code], env=secrets.child_env(), capture_output=True, text=True,
        check=True,
    ).stdout
    seen = json.loads(out)
    # The interpreter may add LC_CTYPE on its own; nothing else may appear.
    assert set(seen) - {"LC_CTYPE"} <= secrets.CHILD_ENV_ALLOWED
    for v in fake_keys:
        assert v not in out


def test_secret_env_names_cover_dev_sandbox_deny_list():
    """Every credential name the dev sandbox unsets is also treated as secret by the code."""
    from pathlib import Path

    settings = json.loads((Path(__file__).resolve().parents[1] / ".claude" / "settings.json")
                          .read_text())
    denied = {e["name"] for e in settings["sandbox"]["credentials"]["envVars"]}
    assert denied
    assert all(secrets.is_secret_name(n) for n in denied)


# --- repository scan (Gate 0 reviewer finding 11) ---------------------------------------

def _git(*args: str) -> str:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout


@pytest.mark.skipif(subprocess.run(["git", "rev-parse"], capture_output=True).returncode != 0,
                    reason="git repo required")
def test_no_secret_in_tracked_files_or_history():
    tracked = _git("ls-files").split()
    assert tracked, "empty file list would make this test vacuous (D-011)"
    history = _git("log", "-p", "--all", "--no-color")
    assert history
    found = secrets.find_secrets(history)
    assert not found, f"secret-like content in git history: {found}"

"""R1: the environment fingerprint is complete, stable, and holds no secrets."""

from aiws.fingerprint import fingerprint
from aiws.secretguard import assert_no_secret


def test_fingerprint_fields_and_stability(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza" + "F" * 35)
    a, b = fingerprint(), fingerprint()
    for key in ("kernel", "python", "sqlite", "bwrap", "packages", "git_commit", "sha256"):
        assert key in a
    assert a["sha256"] == b["sha256"]  # same machine, same answer
    assert a["packages"]["pydantic"]
    assert_no_secret(a)

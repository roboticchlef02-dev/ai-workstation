"""M1 security tests for the L3 sandbox executor (D-005, D-012, Gate 0 Phase 2 list).

Written before src/aiws/executor.py. Every snippet run here is fixed, trusted test code.

Tests marked `needs_l3` need a host where the executor reaches L3 (root + bwrap + setpriv).
Inside the Claude Code dev sandbox nested bwrap hangs, so they skip there with a visible
reason; run them with an approved unsandboxed command (Q14 = b). The fail-closed tests
always run, so a host without isolation is never mistaken for a safe one.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

import pytest

from aiws.executor import ExecLimits, ExecutionDisabled, SandboxExecutor

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def ex() -> SandboxExecutor:
    e = SandboxExecutor(limits=ExecLimits(timeout_s=10))
    if e.isolation_level() != "L3":
        pytest.skip(f"executor not at L3 here ({e.isolation_level()}: {e.why_not_l3()}); "
                    "run unsandboxed (Q14)")
    return e


def run_py(ex: SandboxExecutor, code: str, **kw):
    return ex.run({"main.py": code}, ["python3", "main.py"], **kw)


def last_json(stdout: str):
    return json.loads(stdout.strip().splitlines()[-1])


# --- fail closed (always run) ----------------------------------------------------------

def test_missing_bwrap_disables_execution():
    e = SandboxExecutor(bwrap="/nonexistent/bwrap")
    assert e.isolation_level() != "L3"
    with pytest.raises(ExecutionDisabled):
        e.run({"main.py": "print(1)"}, ["python3", "main.py"])


def test_non_root_orchestrator_disables_execution(monkeypatch):
    """Without root there is no privilege drop, so NPROC can't be enforced (D-005)."""
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    e = SandboxExecutor()
    assert e.isolation_level() != "L3"
    with pytest.raises(ExecutionDisabled):
        e.run({"main.py": "print(1)"}, ["python3", "main.py"])


def test_interpreter_outside_usr_is_refused():
    with pytest.raises(ValueError):
        SandboxExecutor(python="/home/user/venv/bin/python3")


def test_file_names_cannot_escape_workdir():
    e = SandboxExecutor(bwrap="/nonexistent/bwrap")
    for bad in ("../x.py", "/etc/x.py", "a/../../x.py", ""):
        with pytest.raises(ValueError):
            e._check_files({bad: "x"})


# --- basic behaviour -------------------------------------------------------------------

@pytest.mark.needs_l3
def test_runs_code_and_reports_level(ex):
    r = run_py(ex, "print('hello')")
    assert r.returncode == 0 and r.stdout == "hello\n" and r.isolation_level == "L3"
    assert not r.timed_out


@pytest.mark.needs_l3
def test_stdin_is_passed(ex):
    r = run_py(ex, "import sys; print(sys.stdin.read().upper())", stdin="abc")
    assert r.stdout.strip() == "ABC"


# --- isolation -------------------------------------------------------------------------

@pytest.mark.needs_l3
def test_no_network(ex):
    code = """
import json, socket
out = {}
for host, port in [("1.1.1.1", 443), ("8.8.8.8", 53)]:
    try:
        socket.create_connection((host, port), timeout=2); out[host] = "REACHABLE"
    except OSError as e:
        out[host] = "BLOCKED"
try:
    socket.getaddrinfo("example.com", 443); out["dns"] = "RESOLVED"
except OSError:
    out["dns"] = "FAILED"
out["ifaces"] = sorted(l.split(":")[0].strip() for l in open("/proc/net/dev").read().splitlines()[2:])
print(json.dumps(out))
"""
    out = last_json(run_py(ex, code).stdout)
    assert out == {"1.1.1.1": "BLOCKED", "8.8.8.8": "BLOCKED", "dns": "FAILED", "ifaces": ["lo"]}


@pytest.mark.needs_l3
def test_host_filesystem_hidden(ex):
    paths = [str(ROOT), str(ROOT / "benchmarks"), "/home", "/root", "/etc/passwd", "/run",
             "/var", "/proc/1/root/home"]
    code = f"import json, os; print(json.dumps({{p: os.path.exists(p) for p in {paths!r}}}))"
    seen = last_json(run_py(ex, code).stdout)
    assert not any(seen.values()), seen


@pytest.mark.needs_l3
def test_environment_is_clean(ex, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza" + "E" * 35)
    out = last_json(run_py(ex, "import os, json; print(json.dumps(dict(os.environ)))").stdout)
    assert "GEMINI_API_KEY" not in out
    from aiws.executor import SANDBOX_ENV_ALLOWED
    assert set(out) <= SANDBOX_ENV_ALLOWED


@pytest.mark.needs_l3
def test_runs_unprivileged_and_usr_is_read_only(ex):
    code = """
import json, os
r = {"uid": os.getuid(), "euid": os.geteuid()}
try:
    open("/usr/pwned", "w"); r["usr_write"] = True
except OSError:
    r["usr_write"] = False
print(json.dumps(r))
"""
    out = last_json(run_py(ex, code).stdout)
    assert out["uid"] != 0 and out["euid"] != 0 and out["usr_write"] is False


@pytest.mark.needs_l3
def test_no_inherited_file_descriptors(ex):
    out = last_json(run_py(ex, "import os, json; print(json.dumps(sorted(os.listdir('/proc/self/fd'))))").stdout)
    assert set(out) <= {"0", "1", "2", "3"}  # 3 = the fd listdir itself opened


@pytest.mark.needs_l3
def test_host_processes_invisible(ex):
    out = last_json(run_py(ex, "import os, json; print(json.dumps([p for p in os.listdir('/proc') if p.isdigit()]))").stdout)
    assert len(out) <= 4  # sandbox init + python (+ transient); host has many more
    assert str(os.getpid()) not in out or len(out) <= 4


@pytest.mark.needs_l3
def test_cannot_create_new_user_namespace(ex):
    """setns/unshare escape paths: nested user namespaces are disabled."""
    code = """
import ctypes, json, os
libc = ctypes.CDLL(None, use_errno=True)
CLONE_NEWUSER, CLONE_NEWNET = 0x10000000, 0x40000000
res = {}
for name, flag in [("newuser", CLONE_NEWUSER), ("newnet", CLONE_NEWNET)]:
    rc = libc.unshare(flag); res[name] = "OK" if rc == 0 else "EPERM/" + str(ctypes.get_errno())
print(json.dumps(res))
"""
    out = last_json(run_py(ex, code).stdout)
    assert out["newuser"] != "OK" and out["newnet"] != "OK", out


@pytest.mark.needs_l3
def test_host_unix_sockets_unreachable(ex, tmp_path):
    # A path socket in a host temp dir and an abstract socket, both listening on the host.
    path_sock = socket.socket(socket.AF_UNIX)
    path_sock.bind(str(tmp_path / "host.sock"))
    path_sock.listen(1)
    abstract = socket.socket(socket.AF_UNIX)
    abstract.bind("\0aiws-test-abstract")
    abstract.listen(1)
    code = f"""
import json, socket
res = {{}}
for name, addr in [("path", {str(tmp_path / 'host.sock')!r}), ("abstract", "\\0aiws-test-abstract")]:
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect(addr); res[name] = "CONNECTED"
    except OSError:
        res[name] = "BLOCKED"
print(json.dumps(res))
"""
    try:
        out = last_json(run_py(ex, code).stdout)
    finally:
        path_sock.close()
        abstract.close()
    assert out == {"path": "BLOCKED", "abstract": "BLOCKED"}


# --- resource limits -------------------------------------------------------------------

@pytest.mark.needs_l3
def test_timeout_kills_infinite_loop(ex):
    e = SandboxExecutor(limits=ExecLimits(timeout_s=2))
    t0 = time.monotonic()
    r = e.run({"main.py": "while True: pass"}, ["python3", "main.py"])
    assert r.timed_out and r.returncode != 0
    assert time.monotonic() - t0 < 8


@pytest.mark.needs_l3
def test_timeout_kills_children_too(ex):
    code = "import os, time\nif os.fork() == 0:\n    time.sleep(60)\nelse:\n    time.sleep(60)\n"
    e = SandboxExecutor(limits=ExecLimits(timeout_s=2))
    t0 = time.monotonic()
    r = e.run({"main.py": code}, ["python3", "main.py"])
    assert r.timed_out and time.monotonic() - t0 < 8


@pytest.mark.needs_l3
def test_memory_limit(ex):
    r = run_py(ex, "x = bytearray(2 * 1024**3)\nprint('allocated')")
    assert r.returncode != 0 and "allocated" not in r.stdout


@pytest.mark.needs_l3
def test_process_limit_contains_fork_bomb(ex):
    """Bounded fork loop (never an unbounded bomb in tests): successes stay under the cap."""
    code = """
import json, os, time
ok = 0
for _ in range(200):
    try:
        pid = os.fork()
    except OSError:
        break
    if pid == 0:
        time.sleep(3); os._exit(0)
    ok += 1
print(json.dumps({"forks": ok}))
"""
    out = last_json(run_py(ex, code).stdout)
    assert out["forks"] < ex.limits.max_procs


@pytest.mark.needs_l3
def test_file_size_limit(ex):
    code = """
try:
    with open("big.bin", "wb") as f:
        f.write(b"x" * (64 * 1024 * 1024))
    print("WROTE")
except OSError as e:
    print("BLOCKED")
"""
    r = run_py(ex, code)
    assert "WROTE" not in r.stdout


@pytest.mark.needs_l3
def test_output_is_truncated_not_unbounded(ex):
    r = run_py(ex, "import sys\nfor _ in range(200000): sys.stdout.write('y' * 99 + '\\n')")
    assert len(r.stdout.encode()) <= ex.limits.max_output_bytes
    assert r.truncated


@pytest.mark.needs_l3
def test_workdir_is_removed_after_run(ex):
    r = run_py(ex, "import os; print(os.getcwd())")
    assert r.stdout.strip() == "/work"
    assert ex.last_workdir is not None and not ex.last_workdir.exists()

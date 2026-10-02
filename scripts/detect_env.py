"""Phase 0: detect the host and the isolation level that can actually be demonstrated.

Runs only fixed, trusted probe snippets (never model-generated code). Prints JSON.
Usage: python scripts/detect_env.py

Isolation levels (see docs/ENVIRONMENT.md):
  L0  no usable isolation -> arbitrary execution must stay disabled
  L1  child process + clean env + temp dir + memory rlimit (no network isolation)
  L2  L1 + network namespace (no network)
  L3  L2 + filesystem namespace (host fs hidden, bwrap) + enforceable process-count limit
  L4  container/VM runtime available (not required by v0.1)
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile

PY = sys.executable
TIMEOUT = 20

NET_PROBE = (
    "import socket\n"
    "try:\n"
    "    socket.create_connection(('1.1.1.1', 443), timeout=2); print('REACHABLE')\n"
    "except Exception:\n"
    "    print('BLOCKED')\n"
)
MEM_PROBE = (
    "try:\n"
    "    b = bytearray(512 * 1024 * 1024); print('ALLOCATED')\n"
    "except MemoryError:\n"
    "    print('LIMITED')\n"
)
FORK_PROBE = (
    "import os, time\n"
    "pids = []\n"
    "try:\n"
    "    for _ in range(20):\n"
    "        p = os.fork()\n"
    "        if p == 0:\n"
    "            time.sleep(0.5); os._exit(0)\n"
    "        pids.append(p)\n"
    "    print('UNLIMITED')\n"
    "except OSError:\n"
    "    print('LIMITED')\n"
    "for p in pids:\n"
    "    os.waitpid(p, 0)\n"
)


def _run(cmd: list[str], **kw) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, **kw)
        return (r.stdout or "").strip() or f"ERR:{(r.stderr or '').strip()[:200]}"
    except Exception as e:  # noqa: BLE001 - detection must never crash
        return f"ERR:{type(e).__name__}:{e}"


def _ram_gb() -> float | None:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except (ValueError, OSError, AttributeError):
        return None


def _fts5() -> bool:
    try:
        sqlite3.connect(":memory:").execute("create virtual table t using fts5(x)")
        return True
    except sqlite3.Error:
        return False


def _docker_daemon() -> bool:
    if not shutil.which("docker"):
        return False
    return _run(["docker", "info", "--format", "{{.ServerVersion}}"]).startswith("ERR") is False


def _bwrap_cmd(workdir: str, extra: list[str] | None = None) -> list[str]:
    cmd = ["bwrap", "--ro-bind", "/usr", "/usr"]
    for d in ("lib", "lib64", "bin"):
        if os.path.islink(f"/{d}"):
            cmd += ["--symlink", f"usr/{d}", f"/{d}"]
        elif os.path.isdir(f"/{d}"):
            cmd += ["--ro-bind", f"/{d}", f"/{d}"]
    cmd += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--bind", workdir, "/work", "--chdir", "/work",
            "--unshare-all", "--die-with-parent", "--new-session", "--clearenv"]
    return cmd + (extra or [])


def detect() -> dict:
    is_linux = sys.platform.startswith("linux")
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    tools = {t: bool(shutil.which(t)) for t in
             ("unshare", "bwrap", "firejail", "nsjail", "docker", "prlimit", "setpriv", "socat")}
    info: dict = {
        "os": platform.system(),
        "os_release": platform.release(),
        "distro": platform.freedesktop_os_release().get("PRETTY_NAME") if is_linux else None,
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_gb": _ram_gb(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "sqlite_fts5": _fts5(),
        "is_root": is_root,
        "wsl": "microsoft" in platform.release().lower(),
        "tools": tools,
        "docker_daemon": _docker_daemon(),
        "probes": {},
    }
    p = info["probes"]
    python_real = os.path.realpath(PY)

    # Clean environment: child gets an explicitly constructed env.
    out = _run([PY, "-c", "import os, json; print(json.dumps(sorted(os.environ)))"], env={})
    try:
        names = [n for n in json.loads(out) if n != "LC_CTYPE"]  # LC_CTYPE is set by Python itself
        p["clean_env"] = names == []
    except ValueError:
        p["clean_env"] = False

    p["network_baseline"] = _run([PY, "-c", NET_PROBE])

    if is_linux:
        import resource  # noqa: PLC0415 - POSIX only

        def _limit_as():
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))

        p["rlimit_memory"] = _run([PY, "-c", MEM_PROBE], preexec_fn=_limit_as) == "LIMITED"

        if tools["unshare"]:
            ns = ["unshare", "--net"] if is_root else ["unshare", "--user", "--map-root-user", "--net"]
            p["netns"] = _run(ns + ["--", PY, "-c", NET_PROBE])

        if tools["bwrap"]:
            with tempfile.TemporaryDirectory() as wd:
                os.chmod(wd, 0o777)
                probe = ("import os\n" + NET_PROBE +
                         f"print('HOSTFS_VISIBLE' if os.path.exists({os.getcwd()!r}) else 'HOSTFS_HIDDEN')\n"
                         "print('ENV', sorted(k for k in os.environ if k not in ('PWD','LC_CTYPE')))\n")
                p["bwrap"] = _run(_bwrap_cmd(wd) + ["--", python_real, "-c", probe]).splitlines()
                prefix: list[str] = []
                if is_root and tools["setpriv"]:
                    # RLIMIT_NPROC is ignored for uid 0, so drop privileges before bwrap.
                    prefix = ["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups", "--"]
                if tools["prlimit"]:
                    p["bwrap_nproc_limited"] = _run(
                        prefix + ["prlimit", "--nproc=5", "--"] + _bwrap_cmd(wd)
                        + ["--", python_real, "-c", FORK_PROBE]) == "LIMITED"
                    p["nproc_requires_privilege_drop"] = bool(prefix)

    info["isolation_level"] = _level(info)
    return info


def _level(info: dict) -> str:
    p = info["probes"]
    container = bool(info["docker_daemon"])
    # A "BLOCKED" result inside a namespace only proves isolation if the same probe
    # reaches the network without it. Otherwise the check is inconclusive (e.g. when
    # detection itself runs inside another sandbox) and must not raise the level.
    net_demonstrable = p.get("network_baseline") == "REACHABLE"
    l1 = p.get("clean_env") and p.get("rlimit_memory")
    l2 = l1 and net_demonstrable and p.get("netns") == "BLOCKED"
    bw = p.get("bwrap") or []
    l3 = l2 and "BLOCKED" in bw and "HOSTFS_HIDDEN" in bw and p.get("bwrap_nproc_limited")
    if l3:
        level = "L3"
    elif l2:
        level = "L2"
    elif l1:
        level = "L1"
    else:
        level = "L0"
    return level + ("+L4-available" if container else "")


if __name__ == "__main__":
    print(json.dumps(detect(), indent=2))

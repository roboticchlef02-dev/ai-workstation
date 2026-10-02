"""L3 sandbox executor for model-generated code (PLAN 6.4, D-005, D-012).

How a run is isolated:
- privileges dropped with `setpriv` to an unprivileged uid *before* bwrap, so RLIMIT_NPROC
  holds (root ignores it, D-005);
- bwrap: new user/pid/net/ipc/uts/cgroup namespaces, nested user namespaces disabled,
  only /usr (read-only), a fresh /proc, /dev, a tmpfs /tmp and the per-run /work are visible;
- rlimits: address space, processes, file size, open files, CPU, no core dumps;
- environment built from an allowlist (`secretguard.child_env`), never inherited;
- stdout/stderr go to files capped by RLIMIT_FSIZE, then read up to `max_output_bytes`;
- wall-clock timeout kills the whole process group.

Before the first run the executor probes itself with a fixed snippet. Anything short of L3
disables execution (fail closed). The level actually enforced is returned with every result.
"""

from __future__ import annotations

import ctypes
import itertools
import json
import math
import os
import random
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from aiws.secretguard import CHILD_ENV_ALLOWED, child_env

# Each run gets its own unprivileged uid from this pool (no host account uses them).
# Why a pool: the kernel releases a run's process count shortly *after* the run ends, so
# back-to-back runs on one uid hit RLIMIT_NPROC ("Can't fork"). A per-run uid also keeps
# concurrent runs from sharing a process budget (Gate 0 reviewer #8).
SANDBOX_UIDS = range(200_000, 200_064)
# Inside the sandbox: our allowlist, plus PWD (set by bwrap --chdir) and LC_CTYPE (Python).
SANDBOX_ENV_ALLOWED = CHILD_ENV_ALLOWED | {"PWD", "LC_CTYPE"}
_REPO_ROOT = str(Path(__file__).resolve().parents[2])


@dataclass(frozen=True)
class ExecLimits:
    timeout_s: float = 10.0
    memory_mb: int = 512
    max_procs: int = 16
    max_file_mb: int = 16
    max_output_bytes: int = 65536
    nofile: int = 64
    tmpfs_mb: int = 64  # size cap for each of /tmp and /work (both in memory, both bounded)


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    wall_s: float
    isolation_level: str


class ExecutionDisabled(RuntimeError):
    """The host can't provide L3 isolation; model-generated code must not run (D-012)."""


_PROBE = """
import ctypes, json, os, resource
ifaces = sorted(l.split(":")[0].strip() for l in open("/proc/net/dev").read().splitlines()[2:])
host_paths = {host_paths!r}
status = dict(l.split(":", 1) for l in open("/proc/self/status").read().splitlines() if ":" in l)
libc = ctypes.CDLL(None, use_errno=True)
try:
    open("/usr/.aiws-probe", "w"); usr_writable = True
except OSError:
    usr_writable = False
def size_mb(p):
    st = os.statvfs(p); return st.f_blocks * st.f_frsize // (1024 * 1024)
print(json.dumps({{"uid": os.getuid(), "ifaces": ifaces,
                  "hostfs": [p for p in host_paths if os.path.exists(p)],
                  "env": sorted(os.environ),
                  "nproc": resource.getrlimit(resource.RLIMIT_NPROC)[0],
                  "as": resource.getrlimit(resource.RLIMIT_AS)[0],
                  "fsize": resource.getrlimit(resource.RLIMIT_FSIZE)[0],
                  "capeff": status["CapEff"].strip(), "nonewprivs": status["NoNewPrivs"].strip(),
                  "newuser": libc.unshare(0x10000000) == 0, "usr_writable": usr_writable,
                  "tmp_mb": size_mb("/tmp"), "work_mb": size_mb("/work")}}))
"""


class SandboxExecutor:
    def __init__(self, *, limits: ExecLimits = ExecLimits(), bwrap: str | None = None,
                 setpriv: str | None = None, python: str | None = None,
                 base_dir: str | Path = "/tmp/aiws-exec", uid_pool: range = SANDBOX_UIDS,
                 probe_timeout_s: float = 15.0):
        self.limits = limits
        self.bwrap = bwrap or shutil.which("bwrap") or "/usr/bin/bwrap"
        self.setpriv = setpriv or shutil.which("setpriv") or "/usr/bin/setpriv"
        if python is not None:
            self.python: str | None = os.path.realpath(python)
            if not self.python.startswith("/usr/"):
                raise ValueError("the sandbox only mounts /usr; the interpreter must live there")
        else:
            real = os.path.realpath(sys.executable)
            fallback = os.path.realpath("/usr/bin/python3")
            self.python = real if real.startswith("/usr/") else (
                fallback if os.path.exists(fallback) else None)
        self.base = Path(base_dir)
        if not uid_pool or min(uid_pool) < 1000:
            raise ValueError("uid pool must hold unprivileged uids (>= 1000)")
        start = random.randrange(len(uid_pool))
        self._uids = itertools.cycle([*uid_pool[start:], *uid_pool[:start]])
        self.probe_timeout_s = probe_timeout_s
        _become_subreaper()
        self.last_workdir: Path | None = None
        self.last_uid: int | None = None
        self._level: str | None = None
        self._why = ""

    # --- isolation level ---------------------------------------------------------------

    def isolation_level(self) -> str:
        if self._level is None:
            self._level, self._why = self._probe()
        return self._level

    def why_not_l3(self) -> str:
        self.isolation_level()
        return self._why

    def _probe(self) -> tuple[str, str]:
        if os.geteuid() != 0:
            return "L1", "orchestrator is not root: no privilege drop, NPROC unenforceable (D-005)"
        for tool in (self.bwrap, self.setpriv):
            if not (os.path.isfile(tool) and os.access(tool, os.X_OK)):
                return "L1", f"{tool} not found"
        if self.python is None:
            return "L1", "no Python interpreter under /usr"
        code = _PROBE.format(host_paths=[_REPO_ROOT, "/home", "/root", "/etc", "/run", "/var"])
        lim = self.limits
        probe_limits = ExecLimits(timeout_s=self.probe_timeout_s, memory_mb=lim.memory_mb,
                                  max_procs=lim.max_procs, max_file_mb=lim.max_file_mb,
                                  tmpfs_mb=lim.tmpfs_mb)
        try:
            r = self._spawn({"probe.py": code}, [self.python, "probe.py"], "", probe_limits, "?")
        except (OSError, ExecutionDisabled) as e:
            return "L1", f"probe could not start: {type(e).__name__}: {e}"[:200]
        if r.timed_out:
            return "L1", "probe timed out (nested sandbox?)"
        try:
            info = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return "L1", f"probe failed (rc={r.returncode})"
        net = info["ifaces"] == ["lo"]
        failures = []
        if not net:
            failures.append(f"network interfaces {info['ifaces']}")
        if info["hostfs"]:
            failures.append(f"host paths visible {info['hostfs']}")
        if info["uid"] == 0:
            failures.append("runs as uid 0")
        if not set(info["env"]) <= SANDBOX_ENV_ALLOWED:
            failures.append("unexpected environment variables")
        mb = 1024 * 1024
        if info["nproc"] != lim.max_procs:
            failures.append("process limit not applied")
        if info["as"] != lim.memory_mb * mb or info["fsize"] != lim.max_file_mb * mb:
            failures.append("memory or file-size limit not applied")
        if int(info["capeff"], 16) != 0 or info["nonewprivs"] != "1":
            failures.append("capabilities or no-new-privs not dropped")
        if info["newuser"]:
            failures.append("nested user namespaces allowed")
        if info["usr_writable"]:
            failures.append("/usr writable")
        if info["tmp_mb"] > lim.tmpfs_mb or info["work_mb"] > lim.tmpfs_mb:
            failures.append("tmpfs size cap not applied")
        if failures:
            return ("L2" if net else "L1"), "; ".join(failures)
        return "L3", ""

    # --- running code ------------------------------------------------------------------

    @staticmethod
    def _check_files(files: dict[str, str]) -> None:
        for name in files:
            p = PurePosixPath(name)
            if not name or p.is_absolute() or ".." in p.parts or str(p) in (".", ""):
                raise ValueError(f"invalid file name {name!r}")

    def _resolve_argv(self, argv: list[str]) -> list[str]:
        if not argv:
            raise ValueError("empty argv")
        if argv[0] == "python3":
            return [str(self.python), *argv[1:]]
        if not argv[0].startswith("/usr/"):
            raise ValueError("commands must be python3 or an absolute path under /usr")
        return list(argv)

    def run(self, files: dict[str, str], argv: list[str], *, stdin: str = "") -> ExecResult:
        if self.isolation_level() != "L3":
            raise ExecutionDisabled(f"execution disabled below L3 ({self._level}): {self._why}")
        self._check_files(files)
        return self._spawn(files, self._resolve_argv(argv), stdin, self.limits, "L3")

    def _bwrap_args(self, work: Path, names: list[str], limits: ExecLimits) -> list[str]:
        size = str(limits.tmpfs_mb * 1024 * 1024)
        args = [
            "--unshare-all", "--unshare-user", "--disable-userns",
            "--die-with-parent", "--new-session", "--clearenv", "--cap-drop", "ALL",
            "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
            "--symlink", "usr/bin", "/bin",
            "--proc", "/proc", "--dev", "/dev",
            # /tmp and /work live in memory with a size cap; inputs are read-only inside /work.
            "--size", size, "--tmpfs", "/tmp",
            "--size", size, "--tmpfs", "/work",
        ]
        for name in names:
            args += ["--ro-bind", str(work / name), f"/work/{name}"]
        args += ["--chdir", "/work"]
        for k, v in child_env().items():
            args += ["--setenv", k, v]
        return args

    def _ensure_base(self) -> None:
        """The base dir must be a real, root-owned 0711 directory (reviewer #10)."""
        try:
            st = os.lstat(self.base)
        except FileNotFoundError:
            os.mkdir(self.base, 0o711)
            st = os.lstat(self.base)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0:
            raise ExecutionDisabled(f"{self.base} is not a root-owned directory; refusing")
        if stat.S_IMODE(st.st_mode) != 0o711:
            os.chmod(self.base, 0o711)

    def _spawn(self, files: dict[str, str], argv: list[str], stdin: str, limits: ExecLimits,
               level: str) -> ExecResult:
        self._ensure_base()
        work = Path(tempfile.mkdtemp(prefix="w-", dir=self.base))
        io_dir = Path(tempfile.mkdtemp(prefix="io-", dir=self.base))  # root-only (0700)
        self.last_workdir = work
        uid = next(self._uids)
        self.last_uid = uid
        try:
            for name, content in files.items():
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            for p in [work, *work.rglob("*")]:
                os.chown(p, uid, uid)
            os.chmod(work, 0o700)
            (io_dir / "stdin").write_text(stdin)
            cmd = [self.setpriv, f"--reuid={uid}", f"--regid={uid}", "--clear-groups",
                   "--no-new-privs", "--", self.bwrap,
                   *self._bwrap_args(work, list(files), limits), "--", *argv]

            def set_limits() -> None:  # runs in the child, before exec
                mb = 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limits.memory_mb * mb,) * 2)
                resource.setrlimit(resource.RLIMIT_NPROC, (limits.max_procs,) * 2)
                resource.setrlimit(resource.RLIMIT_FSIZE, (limits.max_file_mb * mb,) * 2)
                resource.setrlimit(resource.RLIMIT_NOFILE, (limits.nofile,) * 2)
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                cpu = math.ceil(limits.timeout_s) + 1
                resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))

            t0 = time.monotonic()
            with open(io_dir / "stdin", "rb") as fin, open(io_dir / "stdout", "wb") as fout, \
                    open(io_dir / "stderr", "wb") as ferr:
                proc = subprocess.Popen(cmd, stdin=fin, stdout=fout, stderr=ferr, env=child_env(),
                                        cwd=str(self.base), close_fds=True,
                                        start_new_session=True, preexec_fn=set_limits)
                timed_out = False
                try:
                    proc.wait(timeout=limits.timeout_s)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
            wall = time.monotonic() - t0
            out, t_out = _read_capped(io_dir / "stdout", limits.max_output_bytes)
            err, t_err = _read_capped(io_dir / "stderr", limits.max_output_bytes)
            return ExecResult(returncode=proc.returncode, stdout=out, stderr=err,
                              timed_out=timed_out, truncated=t_out or t_err, wall_s=wall,
                              isolation_level=level)
        finally:
            _kill_uid(uid)
            _remove(work)
            _remove(io_dir)


_PR_SET_CHILD_SUBREAPER = 36


def _become_subreaper() -> None:
    """Orphaned sandbox processes are reparented to this process instead of the host's init,
    so we can reap them. Otherwise their zombies linger and count against the run uid's
    RLIMIT_NPROC (the real cause of the old "Can't fork" failures)."""
    try:
        ctypes.CDLL(None, use_errno=True).prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)
    except (OSError, AttributeError):
        pass


def _kill_uid(uid: int) -> None:
    """Kill, and reap if they are ours, all processes of the run's uid (reviewer #9).
    Never raises."""
    me = os.getpid()
    for _ in range(20):
        found = False
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/status") as f:
                    fields = dict(ln.split(":", 1) for ln in f if ":" in ln)
                if int(fields["Uid"].split()[0]) != uid:
                    continue
                found = True
                if fields["State"].strip().startswith("Z"):
                    if int(fields["PPid"]) == me:
                        os.waitpid(int(pid), os.WNOHANG)
                else:
                    os.kill(int(pid), signal.SIGKILL)
            except (OSError, KeyError, ValueError, ChildProcessError):
                continue
        if not found:
            return
        time.sleep(0.02)


def _remove(path: Path) -> None:
    """Delete a run directory. Never raises (a deep tree must not crash the run, reviewer #3)."""
    try:
        shutil.rmtree(path)
    except BaseException:  # noqa: BLE001  (RecursionError on very deep trees, etc.)
        subprocess.run(["rm", "-rf", "--one-file-system", "--", str(path)],
                       capture_output=True, check=False)


def _read_capped(path: Path, limit: int) -> tuple[str, bool]:
    with open(path, "rb") as f:
        data = f.read(limit + 1)
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", errors="replace"), truncated

# Environment and isolation — Phase 0 measurements (2026-10-02)

**Measured host: the Claude Code cloud container for this session, not Ridha's PC.** Ridha's PC has not been measured (see `QUESTIONS.md` Q1).

## Host

| Item | Value |
|---|---|
| OS | Ubuntu 24.04.4 LTS, kernel 6.18.44 (Firecracker microVM), x86_64 |
| CPU / RAM | 4 vCPU / 15.7 GB, no swap |
| Disk | ~30 GB free (per-session allowance) |
| Python | 3.11.15 default; 3.12, 3.13 also present |
| SQLite | 3.45.1, FTS5 works |
| User | root inside the container |
| Docker | CLI present, **no daemon** |
| Lifetime | **Ephemeral.** Container is reclaimed when idle; only git-pushed files survive |

## Isolation evidence

Probed by hand on 2026-10-02, *before* the Claude Code dev sandbox was switched on. All probes ran fixed, trusted snippets; no model-generated code was executed.

| Capability | Result | Evidence |
|---|---|---|
| Clean child environment (`env={}`) | ✅ | child sees only `LC_CTYPE` |
| Memory limit (`RLIMIT_AS` 256 MB) | ✅ | 512 MB allocation → `MemoryError` |
| Network namespace (`unshare --net`) | ✅ | baseline reached 1.1.1.1:443; inside ns → `ENETUNREACH` |
| Filesystem namespace (`bwrap --unshare-all --clearenv`) | ✅ | host repo path invisible; `/` = only `/usr`, `/proc`, `/dev`, `/tmp`, work dir; env = `PATH` only |
| Process-count limit (`RLIMIT_NPROC`) as root | ❌ | 20/20 forks succeeded: root ignores NPROC, **even inside `bwrap --uid 65534`** |
| Process-count limit after `setpriv` to uid 65534, then bwrap | ✅ | fork blocked after 2 (`EAGAIN`) |
| cgroup v1 memory/pids controllers | present, delegation untested | — |
| Container/VM runtime (Docker) | ❌ | no daemon |

**Achievable isolation level: L3** (see scale below), shown by manual probes. The executor that actually enforces it doesn't exist yet; it is Phase 2 work, and Gate 1 must show it with security tests.

`bubblewrap` and `socat` were **installed by me via apt in this session**. They disappear when the container is recycled unless the environment's setup script installs them (Q8).

### Isolation scale (recorded as `isolation_level` on every experiment record)

| Level | Meaning |
|---|---|
| L0 | No usable isolation → arbitrary execution stays **disabled** |
| L1 | Child process + clean env + temp dir + memory rlimit + timeout; no network isolation |
| L2 | L1 + network namespace (shown to block a network that is otherwise reachable) |
| L3 | L2 + filesystem namespace (host hidden) + enforceable process-count limit (privileges dropped) |
| L4 | Container/VM runtime (not required for v0.1) |

### Limitations of L3 here

- **Shared kernel.** bwrap uses namespaces, not a VM. A kernel exploit escapes it. The outer Firecracker VM is the next boundary, and it belongs to the cloud provider, not to us.
- **Root outside.** The orchestrator runs as root. The executor must drop privileges (`setpriv`) before entering bwrap, or NPROC limits are silently ignored.
- **`/usr` is visible read-only** inside the sandbox (interpreter and site-packages). Nothing secret lives there today. Re-check whenever dependencies change.
- **No CPU-time isolation from the host** beyond rlimit + wall-clock timeout. Timing-based metrics (latency) are noisy on a shared VM.
- **Not persistent.** Without the setup script, a fresh container has no bwrap, and the executor must fall back to L2 or disable execution.

## Network (cloud environment policy, probed without credentials, $0)

| Host | Result |
|---|---|
| api.anthropic.com | reachable (HTTP 401 without key) |
| generativelanguage.googleapis.com (Gemini) | reachable (HTTP 403 without key) |
| **api.openai.com** | **blocked by environment network policy** (proxy 403 on CONNECT) |
| **api.deepseek.com** | **blocked by environment network policy** |
| pypi.org | reachable outside the dev sandbox; **not** from sandboxed commands (see below) |
| arxiv.org (WebFetch) | blocked |

## Claude Code dev sandbox (protects the repo from the builder)

- Claude Code **v2.1.287**. Settings syntax checked against the current docs (`code.claude.com/docs/en/sandboxing`, `/permissions`, `/settings-reference`), not guessed.
- `.claude/settings.json`: `Read`/`Edit` deny rules for `.env` variants, `secrets/`, `benchmarks/held_out/`. Per the docs, `Read` deny rules are also added to the OS sandbox `denyRead`. `sandbox.enabled: true`. Provider key env vars are **unset** in sandboxed commands. Edits to the safety config require approval (`ask`).
- The sandbox **took effect live in this session**. Its resolved config was shown to me and lists the protected paths as `denyOnly`.
- Side effects observed: nested bwrap hangs inside it, so `scripts/detect_env.py` reports a lower level when run sandboxed. The detector is now conservative: network-namespace evidence counts only if the baseline network is reachable. `pip install` from sandboxed commands fails, so dev dependencies must come from the setup script (Q8).
- What it does **not** cover: Claude Code's own file tools rely on the permission rules, not the OS sandbox. On Linux, wildcard read rules are expanded only to files that exist when the rule loads.

Re-run detection on any new machine: `python scripts/detect_env.py` (run it outside the Claude Code sandbox to measure the host itself).

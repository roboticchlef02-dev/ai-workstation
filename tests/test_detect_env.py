import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("detect_env", ROOT / "scripts" / "detect_env.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_detect_reports_required_fields():
    info = _load().detect()
    for key in ("os", "cpu_count", "ram_gb", "python", "sqlite_fts5", "isolation_level", "probes"):
        assert key in info
    assert info["isolation_level"].split("+")[0] in {"L0", "L1", "L2", "L3"}


def test_level_requires_demonstrated_probes():
    mod = _load()
    base = {"docker_daemon": False}
    assert mod._level({**base, "probes": {}}) == "L0"
    l1 = {"clean_env": True, "rlimit_memory": True, "network_baseline": "REACHABLE"}
    assert mod._level({**base, "probes": l1}) == "L1"
    # A network namespace that does not actually block is not L2.
    assert mod._level({**base, "probes": {**l1, "netns": "REACHABLE"}}) == "L1"
    # Regression: if the network was unreachable anyway, "BLOCKED" proves nothing.
    offline = {**l1, "network_baseline": "BLOCKED", "netns": "BLOCKED"}
    assert mod._level({**base, "probes": offline}) == "L1"
    l2 = {**l1, "netns": "BLOCKED"}
    assert mod._level({**base, "probes": l2}) == "L2"
    # bwrap without an enforceable process limit is not L3.
    bw = ["BLOCKED", "HOSTFS_HIDDEN"]
    assert mod._level({**base, "probes": {**l2, "bwrap": bw, "bwrap_nproc_limited": False}}) == "L2"
    assert mod._level({**base, "probes": {**l2, "bwrap": bw, "bwrap_nproc_limited": True}}) == "L3"

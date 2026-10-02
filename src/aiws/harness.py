"""Test harness copied into the sandbox next to `solution.py`. Trusted code, stdlib only.

Usage inside the sandbox: python3 harness.py <marker> <entry_point>
Reads `inputs.json` (a list of argument lists), calls the entry point on each, and prints one
line `<marker>{"results": [...]}`. Expected values never enter the sandbox: comparison
happens outside (`aiws.benchmark.compare`), so code under test can't read or forge them.
"""

import contextlib
import io
import json
import sys


def main() -> None:
    marker, entry = sys.argv[1], sys.argv[2]
    with open("inputs.json") as f:
        inputs = json.load(f)
    out = sys.stdout
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import solution  # noqa: PLC0415  (the code under test)
        fn = getattr(solution, entry)
    except BaseException as e:  # noqa: BLE001  (SyntaxError, SystemExit, missing name…)
        out.write(marker + json.dumps({"load_error": f"{type(e).__name__}: {e}"[:500]}) + "\n")
        return
    results = []
    for args in inputs:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                value = fn(*args)
            json.dumps(value)
            results.append({"ok": True, "value": value})
        except BaseException as e:  # noqa: BLE001
            results.append({"ok": False, "error": f"{type(e).__name__}: {e}"[:300]})
    out.write(marker + json.dumps({"results": results}) + "\n")
    out.flush()


if __name__ == "__main__":
    main()

"""Telemetry store (PLAN 6.10). Every record passes the secret guard before it is written.

M1 holds call-level records; run-level records are added with the experiment runner.
Records carry hashes of prompts and responses, not the texts.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiws.secretguard import assert_no_secret


class Telemetry:
    def __init__(self, path: Path | str):
        self.path = str(path)
        with sqlite3.connect(self.path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "ts TEXT NOT NULL, experiment_id TEXT, run_id TEXT, arm TEXT, "
                        "task_id TEXT, record_json TEXT NOT NULL)")

    def write_call(self, record: Mapping[str, Any]) -> None:
        assert_no_secret(record)
        body = json.dumps(record, sort_keys=True)
        with sqlite3.connect(self.path) as con:
            con.execute("INSERT INTO calls (ts, experiment_id, run_id, arm, task_id, record_json) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (datetime.now(timezone.utc).isoformat(), record.get("experiment_id"),
                         record.get("run_id"), record.get("arm"), record.get("task_id"), body))

    def calls(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as con:
            rows = con.execute("SELECT record_json FROM calls ORDER BY id").fetchall()
        return [json.loads(r[0]) for r in rows]

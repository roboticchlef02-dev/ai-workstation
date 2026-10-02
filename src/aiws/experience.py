"""Experience log: the learning plane's record of what was tried on TRAIN tasks (D-027).

One row per strategy attempt: which option ran, on which task category, and the evaluator's
verdict, with the versions needed to tell results apart (law 6). Code text is not stored,
only its hash. Rows from any pool other than TRAIN are refused, so evaluation and held-out
outcomes never reach learning (PLAN 5.1). A frozen log refuses all writes.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aiws.secretguard import assert_no_secret

SCHEMA_VERSION = 1


class ExperienceRefused(Exception):
    pass


class ExperienceRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str
    pool: Literal["TRAIN"]
    task_id: str
    category: str
    difficulty: int
    option: str
    strategy_id: str
    strategy_version: int
    strategy_sha256: str = Field(min_length=64, max_length=64)
    models: list[str]
    passed: bool
    hidden: str
    visible_pass: bool
    model_calls: int
    rounds_used: int
    generated_tests: int
    shadow_usd: float
    evaluator_version: str
    benchmark_sha256: str
    template_version: str
    code_sha256: str


class ExperienceLog:
    def __init__(self, path: Path | str, *, frozen: bool = False):
        self.path, self.frozen = str(path), frozen
        with sqlite3.connect(self.path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS experience (id INTEGER PRIMARY KEY "
                        "AUTOINCREMENT, ts TEXT NOT NULL, schema INTEGER NOT NULL, run_id TEXT, "
                        "pool TEXT NOT NULL, task_id TEXT, category TEXT, option TEXT, "
                        "passed INTEGER, record_json TEXT NOT NULL)")

    def write(self, row: ExperienceRow) -> None:
        if self.frozen:
            raise ExperienceRefused("experience log is frozen")
        if row.pool != "TRAIN":  # also enforced by the schema
            raise ExperienceRefused(f"pool {row.pool} may not enter the experience log")
        record = row.model_dump(mode="json")
        assert_no_secret(record)
        with sqlite3.connect(self.path) as con:
            con.execute("INSERT INTO experience (ts, schema, run_id, pool, task_id, category, "
                        "option, passed, record_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (datetime.now(timezone.utc).isoformat(), SCHEMA_VERSION, row.run_id,
                         row.pool, row.task_id, row.category, row.option, int(row.passed),
                         json.dumps(record, sort_keys=True)))

    def rows(self, run_id: str | None = None) -> list[ExperienceRow]:
        with sqlite3.connect(self.path) as con:
            q = "SELECT record_json FROM experience WHERE pool = 'TRAIN'"
            args: tuple[str, ...] = ()
            if run_id is not None:
                q, args = q + " AND run_id = ?", (run_id,)
            got = con.execute(q + " ORDER BY id", args).fetchall()
        return [ExperienceRow(**json.loads(r[0])) for r in got]

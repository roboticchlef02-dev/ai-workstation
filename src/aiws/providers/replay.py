"""Record/replay cache keyed by (provider, full request) (PLAN 6.1).

- mode "record": cache-through. A hit is replayed; a miss calls the inner provider and stores it.
- mode "replay": cache only. A miss raises ReplayMiss; it never falls through to a live call.
Replayed responses carry `replayed=True`. They are free and reproducible, and never count as
final results unless Ridha approves (PLAN 6.1).
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from aiws.providers.base import Capabilities, GenerateRequest, GenerateResponse, ModelProvider
from aiws.secretguard import assert_no_secret


class ReplayMiss(LookupError):
    pass


class ReplayStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        with sqlite3.connect(self.path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS replay (key TEXT PRIMARY KEY, "
                        "response_json TEXT NOT NULL, recorded_at TEXT NOT NULL)")

    @staticmethod
    def key(provider: str, req: GenerateRequest) -> str:
        return hashlib.sha256(f"{provider}\n{req.canonical_json()}".encode()).hexdigest()

    def get(self, key: str) -> GenerateResponse | None:
        with sqlite3.connect(self.path) as con:
            row = con.execute("SELECT response_json FROM replay WHERE key = ?", (key,)).fetchone()
        return None if row is None else GenerateResponse.model_validate_json(row[0])

    def put(self, key: str, resp: GenerateResponse) -> None:
        assert_no_secret(resp)  # a response that looks like it holds a key is not cached
        with sqlite3.connect(self.path) as con:
            con.execute("INSERT OR REPLACE INTO replay VALUES (?, ?, ?)",
                        (key, resp.model_dump_json(), datetime.now(timezone.utc).isoformat()))


class RecordReplayProvider(ModelProvider):
    def __init__(self, inner: ModelProvider, store: ReplayStore,
                 mode: Literal["record", "replay"]):
        if mode not in ("record", "replay"):
            raise ValueError(f"unknown replay mode {mode!r}")
        self.inner, self.store, self.mode = inner, store, mode
        self.name = inner.name
        self.billing_tier = inner.billing_tier

    def get_model_id(self) -> str:
        return self.inner.get_model_id()

    def get_capabilities(self, model_id: str | None = None) -> Capabilities:
        return self.inner.get_capabilities(model_id)

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        key = ReplayStore.key(self.inner.name, req)
        hit = self.store.get(key)
        if hit is not None:
            return hit.model_copy(update={"replayed": True, "latency_s": 0.0})
        if self.mode == "replay":
            raise ReplayMiss(f"no recorded response for request {req.sha256()[:16]}")
        resp = self.inner.generate(req)
        self.store.put(key, resp)
        return resp

    def _generate(self, req: GenerateRequest, sampling: dict[str, Any]) -> GenerateResponse:
        raise NotImplementedError("RecordReplayProvider overrides generate()")

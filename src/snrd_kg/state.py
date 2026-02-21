from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class BatchState:
    window: str
    page: int
    batch: int
    ids: list[str]
    applied: bool
    cypher_path: str
    cypher_hash: str
    config_hash: str


class StateProtocol(Protocol):
    def upsert_batch(self, state: BatchState) -> None: ...
    def get_batch(self, window: str, page: int, batch: int) -> BatchState | None: ...
    def list_unapplied(self, from_window: str | None = None, until_window: str | None = None) -> list[BatchState]: ...


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS batch_state (
                window TEXT NOT NULL,
                page INTEGER NOT NULL,
                batch INTEGER NOT NULL,
                ids_json TEXT NOT NULL,
                applied INTEGER NOT NULL,
                cypher_path TEXT NOT NULL,
                cypher_hash TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (window, page, batch)
            )
            """
        )
        self.conn.commit()

    @staticmethod
    def hash_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def hash_config(config: dict[str, Any]) -> str:
        return StateStore.hash_text(json.dumps(config, sort_keys=True, ensure_ascii=False))

    def upsert_batch(self, state: BatchState) -> None:
        self.conn.execute(
            """
            INSERT INTO batch_state(window,page,batch,ids_json,applied,cypher_path,cypher_hash,config_hash)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(window,page,batch) DO UPDATE SET
                ids_json=excluded.ids_json,
                applied=excluded.applied,
                cypher_path=excluded.cypher_path,
                cypher_hash=excluded.cypher_hash,
                config_hash=excluded.config_hash,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                state.window,
                state.page,
                state.batch,
                json.dumps(state.ids, ensure_ascii=False),
                int(state.applied),
                state.cypher_path,
                state.cypher_hash,
                state.config_hash,
            ),
        )
        self.conn.commit()

    def get_batch(self, window: str, page: int, batch: int) -> BatchState | None:
        row = self.conn.execute(
            "SELECT window,page,batch,ids_json,applied,cypher_path,cypher_hash,config_hash FROM batch_state WHERE window=? AND page=? AND batch=?",
            (window, page, batch),
        ).fetchone()
        if not row:
            return None
        return BatchState(row[0], row[1], row[2], json.loads(row[3]), bool(row[4]), row[5], row[6], row[7])

    def list_unapplied(self, from_window: str | None = None, until_window: str | None = None) -> list[BatchState]:
        query = "SELECT window,page,batch,ids_json,applied,cypher_path,cypher_hash,config_hash FROM batch_state WHERE applied=0"
        params: list[Any] = []
        if from_window:
            query += " AND window >= ?"
            params.append(from_window)
        if until_window:
            query += " AND window <= ?"
            params.append(until_window)
        rows = self.conn.execute(query + " ORDER BY window,page,batch", params).fetchall()
        return [BatchState(r[0], r[1], r[2], json.loads(r[3]), bool(r[4]), r[5], r[6], r[7]) for r in rows]


class JsonStateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, entries: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert_batch(self, state: BatchState) -> None:
        entries = self._load()
        key = (state.window, state.page, state.batch)
        payload = asdict(state)
        for idx, entry in enumerate(entries):
            if (entry["window"], entry["page"], entry["batch"]) == key:
                entries[idx] = payload
                self._save(entries)
                return
        entries.append(payload)
        self._save(entries)

    def get_batch(self, window: str, page: int, batch: int) -> BatchState | None:
        for entry in self._load():
            if (entry["window"], entry["page"], entry["batch"]) == (window, page, batch):
                return BatchState(**entry)
        return None

    def list_unapplied(self, from_window: str | None = None, until_window: str | None = None) -> list[BatchState]:
        out: list[BatchState] = []
        for entry in self._load():
            if entry["applied"]:
                continue
            if from_window and entry["window"] < from_window:
                continue
            if until_window and entry["window"] > until_window:
                continue
            out.append(BatchState(**entry))
        return sorted(out, key=lambda x: (x.window, x.page, x.batch))

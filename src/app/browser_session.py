from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any


class BrowserSessionStore:
    """Durable single-host sessions and atomic one-use tickets; raw secrets are never stored."""

    def __init__(self, path: str, maximum_records: int = 10000) -> None:
        if not path or path == ":memory:" or maximum_records < 1:
            raise ValueError("A durable browser session database and finite capacity are required")

        self.path = path
        self.maximum_records = maximum_records

    @staticmethod
    def _digest(secret: str) -> str:
        return hashlib.sha256(secret.encode()).hexdigest()

    def _query(
        self, operation: str, kind: str, secret: str, payload: dict[str, Any], ttl: float
    ) -> dict[str, Any] | None:
        key = self._digest(secret)
        Path(self.path).touch(mode=0o600, exist_ok=True)

        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS browser_records (kind TEXT, key TEXT, "
                "payload TEXT, expires REAL, PRIMARY KEY(kind, key))"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS browser_records_expiry ON browser_records(expires)"
            )
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM browser_records WHERE expires <= ?", (time.time(),))

            if operation == "put":
                if (
                    db.execute("SELECT count(*) FROM browser_records").fetchone()[0]
                    >= self.maximum_records
                ):
                    raise ValueError("Browser session capacity exceeded")

                db.execute(
                    "INSERT INTO browser_records VALUES (?, ?, ?, ?)",
                    (kind, key, json.dumps(payload), time.time() + ttl),
                )
                return None

            if operation == "update":
                db.execute(
                    "UPDATE browser_records SET payload=? WHERE kind=? AND key=?",
                    (json.dumps(payload), kind, key),
                )

            row = db.execute(
                "SELECT payload FROM browser_records WHERE kind=? AND key=?", (kind, key)
            ).fetchone()

            if operation == "consume":
                db.execute("DELETE FROM browser_records WHERE kind=? AND key=?", (kind, key))

            return json.loads(row[0]) if row else None

    async def put(self, kind: str, payload: dict[str, Any], ttl: float) -> str:
        secret = secrets.token_urlsafe(32)
        await asyncio.to_thread(self._query, "put", kind, secret, payload, ttl)
        return secret

    async def get(self, kind: str, secret: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._query, "get", kind, secret, {}, 0)

    async def consume(self, kind: str, secret: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._query, "consume", kind, secret, {}, 0)

    async def update(self, kind: str, secret: str, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self._query, "update", kind, secret, payload, 0)

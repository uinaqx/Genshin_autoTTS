from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path


class AudioCache:
    def __init__(self, root: Path, max_bytes: int) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.files = root / "objects"
        self.tmp = root / "tmp"
        self.files.mkdir(parents=True, exist_ok=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "cache.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS audio_cache (
                    cache_key TEXT PRIMARY KEY,
                    relative_path TEXT NOT NULL,
                    codec TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    last_access REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )

    def get(self, cache_key: str) -> tuple[Path, str, str] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT relative_path, codec, provider FROM audio_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            path = self.root / row[0]
            if not path.exists():
                db.execute("DELETE FROM audio_cache WHERE cache_key = ?", (cache_key,))
                return None
            db.execute(
                "UPDATE audio_cache SET last_access = ? WHERE cache_key = ?",
                (time.time(), cache_key),
            )
            return path, row[1], row[2]

    def temporary_path(self, cache_key: str, suffix: str) -> Path:
        return self.tmp / f"{cache_key}{suffix}"

    def put(self, cache_key: str, source: Path, codec: str, provider: str) -> Path:
        suffix = source.suffix.lower()
        target_dir = self.files / cache_key[:2] / cache_key[2:4]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{cache_key}{suffix}"
        if source.resolve() != target.resolve():
            shutil.move(str(source), str(target))
        now = time.time()
        size = target.stat().st_size
        relative = str(target.relative_to(self.root))
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO audio_cache(cache_key, relative_path, codec, provider, size_bytes, last_access, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    relative_path=excluded.relative_path,
                    codec=excluded.codec,
                    provider=excluded.provider,
                    size_bytes=excluded.size_bytes,
                    last_access=excluded.last_access
                """,
                (cache_key, relative, codec, provider, size, now, now),
            )
        self.evict()
        return target

    def total_bytes(self) -> int:
        with self._connect() as db:
            row = db.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM audio_cache").fetchone()
            return int(row[0])

    def evict(self) -> None:
        with self._connect() as db:
            total = int(db.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM audio_cache").fetchone()[0])
            if total <= self.max_bytes:
                return
            rows = db.execute(
                "SELECT cache_key, relative_path, size_bytes FROM audio_cache ORDER BY last_access ASC"
            ).fetchall()
            for cache_key, relative_path, size_bytes in rows:
                path = self.root / relative_path
                path.unlink(missing_ok=True)
                db.execute("DELETE FROM audio_cache WHERE cache_key = ?", (cache_key,))
                total -= int(size_bytes)
                if total <= self.max_bytes:
                    break

    def clear(self) -> None:
        if self.files.exists():
            shutil.rmtree(self.files)
        self.files.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("DELETE FROM audio_cache")

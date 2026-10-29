from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "smartlex_history.db")


def get_db_path() -> str:
    return os.environ.get("SMARTLEX_DB_PATH", DEFAULT_DB_PATH)


def configure_database(path: Optional[str] = None) -> str:
    db_path = path or get_db_path()
    os.environ["SMARTLEX_DB_PATH"] = db_path
    return db_path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    os.makedirs(os.path.dirname(get_db_path()) or ".", exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                analysis_type TEXT NOT NULL,
                status TEXT NOT NULL,
                token_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )


def _record_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    payload = json.loads(row["result_json"] or "{}")
    return {
        "id": row["id"],
        "source": row["source"],
        "analysis_type": row["analysis_type"],
        "status": row["status"],
        "token_count": row["token_count"],
        "error_count": row["error_count"],
        "created_at": row["created_at"],
        "summary": row["summary"],
        "result": payload,
    }


def _build_summary(result: Optional[Dict[str, Any]], source: str = "") -> str:
    if result is None:
        result = {}
    if result.get("diagnoses"):
        return f"{len(result['diagnoses'])} diagnosis items"
    if result.get("suggestions"):
        return f"{len(result['suggestions'])} suggestions"
    if result.get("statements"):
        return f"{len(result['statements'])} statements"
    if source:
        return "Analysis saved"
    return "Empty source"


def save_analysis_record(
    source: str,
    analysis_type: str = "diagnosis",
    status: str = "unknown",
    token_count: int = 0,
    error_count: int = 0,
    result: Optional[Dict[str, Any]] = None,
    summary: Optional[str] = None,
) -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = result or {}
    summary_text = summary or _build_summary(payload, source)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO analysis_records (
                source, analysis_type, status, token_count, error_count, created_at, summary, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source, analysis_type, status, token_count, error_count, timestamp, summary_text, json.dumps(payload)),
        )
        record_id = cursor.lastrowid
    return get_analysis_record(record_id)


def list_analysis_records(limit: int = 20) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM analysis_records ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_record_to_dict(row) for row in rows]


def get_analysis_record(record_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM analysis_records WHERE id = ?",
            (record_id,),
        ).fetchone()
    if row is None:
        raise KeyError(record_id)
    return _record_to_dict(row)


def delete_analysis_record(record_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM analysis_records WHERE id = ?", (record_id,))
    return cursor.rowcount > 0


initialize_database()

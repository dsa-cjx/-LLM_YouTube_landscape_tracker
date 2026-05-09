from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "landscape.sqlite"


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                channel TEXT,
                channel_category TEXT,
                url TEXT,
                published TEXT,
                summary TEXT,
                raw_feed_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transcripts (
                video_id TEXT PRIMARY KEY,
                transcript TEXT,
                language TEXT,
                status TEXT,
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(video_id) REFERENCES videos(video_id)
            );

            CREATE TABLE IF NOT EXISTS analyses (
                video_id TEXT PRIMARY KEY,
                analysis_json TEXT,
                status TEXT,
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(video_id) REFERENCES videos(video_id)
            );
            """
        )


def upsert_video(video: dict[str, Any]) -> None:
    init_db()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO videos (
                video_id,
                title,
                channel,
                channel_category,
                url,
                published,
                summary,
                raw_feed_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(video_id) DO UPDATE SET
                title = excluded.title,
                channel = excluded.channel,
                channel_category = excluded.channel_category,
                url = excluded.url,
                published = excluded.published,
                summary = excluded.summary,
                raw_feed_json = excluded.raw_feed_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                video["video_id"],
                video.get("title", ""),
                video.get("channel", ""),
                video.get("channel_category", ""),
                video.get("url", ""),
                video.get("published", ""),
                video.get("summary", ""),
                json.dumps(video.get("raw", {}), ensure_ascii=False),
            ),
        )


def upsert_transcript(
    video_id: str,
    transcript: str | None,
    language: str | None,
    status: str,
    error: str | None = None,
) -> None:
    init_db()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO transcripts (
                video_id,
                transcript,
                language,
                status,
                error,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(video_id) DO UPDATE SET
                transcript = excluded.transcript,
                language = excluded.language,
                status = excluded.status,
                error = excluded.error,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                video_id,
                transcript,
                language,
                status,
                error,
            ),
        )


def upsert_analysis(
    video_id: str,
    analysis_json: dict[str, Any] | None,
    status: str,
    error: str | None = None,
) -> None:
    init_db()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO analyses (
                video_id,
                analysis_json,
                status,
                error,
                updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(video_id) DO UPDATE SET
                analysis_json = excluded.analysis_json,
                status = excluded.status,
                error = excluded.error,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                video_id,
                json.dumps(analysis_json, ensure_ascii=False) if analysis_json else None,
                status,
                error,
            ),
        )


def get_videos_without_transcripts(limit: int = 20) -> list[dict[str, Any]]:
    init_db()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT v.*
            FROM videos v
            LEFT JOIN transcripts t ON v.video_id = t.video_id
            WHERE t.video_id IS NULL
            ORDER BY v.published DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_videos_ready_for_analysis(limit: int = 10) -> list[dict[str, Any]]:
    init_db()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                v.*,
                t.transcript,
                t.language,
                t.status AS transcript_status
            FROM videos v
            JOIN transcripts t ON v.video_id = t.video_id
            LEFT JOIN analyses a ON v.video_id = a.video_id
            WHERE
                a.video_id IS NULL
                AND t.status = 'ok'
                AND t.transcript IS NOT NULL
                AND LENGTH(t.transcript) > 100
            ORDER BY v.published DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_all_videos_joined() -> list[dict[str, Any]]:
    init_db()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                v.video_id,
                v.title,
                v.channel,
                v.channel_category,
                v.url,
                v.published,
                v.summary,
                t.status AS transcript_status,
                t.language AS transcript_language,
                a.status AS analysis_status,
                a.analysis_json
            FROM videos v
            LEFT JOIN transcripts t ON v.video_id = t.video_id
            LEFT JOIN analyses a ON v.video_id = a.video_id
            ORDER BY v.published DESC
            """
        ).fetchall()

    result: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)

        if item.get("analysis_json"):
            try:
                item["analysis"] = json.loads(item["analysis_json"])
            except json.JSONDecodeError:
                item["analysis"] = None
        else:
            item["analysis"] = None

        item.pop("analysis_json", None)
        result.append(item)

    return result
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from db import get_videos_without_transcripts, init_db, upsert_transcript


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
DATA_DIR = ROOT / "data"
TRANSCRIPTS_JSON = DATA_DIR / "transcripts.json"

load_dotenv(ENV_PATH)


def transcript_to_text(items: list[dict]) -> str:
    parts = []

    for item in items:
        text = item.get("text", "")
        text = text.replace("\n", " ").strip()

        if text:
            parts.append(text)

    return " ".join(parts)


def fetch_transcript(video_id: str) -> tuple[str, str]:
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

    preferred_langs = ["en", "en-US", "zh-Hans", "zh", "zh-CN"]

    try:
        transcript = transcript_list.find_transcript(preferred_langs)
    except NoTranscriptFound:
        transcript = transcript_list.find_generated_transcript(preferred_langs)

    items = transcript.fetch()
    text = transcript_to_text(items)

    return text, transcript.language_code


def main() -> None:
    init_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    limit = int(os.getenv("MAX_TRANSCRIPTS_PER_RUN", "20"))
    videos = get_videos_without_transcripts(limit=limit)

    print(f"Videos without transcripts: {len(videos)}")

    results = []

    for video in videos:
        video_id = video["video_id"]
        title = video.get("title", "")

        print(f"Fetching transcript: {video_id} | {title}")

        try:
            text, language = fetch_transcript(video_id)

            if not text.strip():
                upsert_transcript(
                    video_id=video_id,
                    transcript=None,
                    language=language,
                    status="empty",
                    error="Transcript is empty.",
                )

                results.append(
                    {
                        "video_id": video_id,
                        "status": "empty",
                        "language": language,
                    }
                )

                continue

            upsert_transcript(
                video_id=video_id,
                transcript=text,
                language=language,
                status="ok",
            )

            results.append(
                {
                    "video_id": video_id,
                    "status": "ok",
                    "language": language,
                    "length": len(text),
                }
            )

        except TranscriptsDisabled as exc:
            upsert_transcript(
                video_id=video_id,
                transcript=None,
                language=None,
                status="disabled",
                error=str(exc),
            )

            results.append(
                {
                    "video_id": video_id,
                    "status": "disabled",
                    "error": str(exc),
                }
            )

        except Exception as exc:
            upsert_transcript(
                video_id=video_id,
                transcript=None,
                language=None,
                status="error",
                error=str(exc),
            )

            results.append(
                {
                    "video_id": video_id,
                    "status": "error",
                    "error": str(exc),
                }
            )

    TRANSCRIPTS_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Transcript fetching done.")


if __name__ == "__main__":
    main()
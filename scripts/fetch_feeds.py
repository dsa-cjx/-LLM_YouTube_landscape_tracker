from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import feedparser
import yaml

from db import init_db, upsert_video


ROOT = Path(__file__).resolve().parents[1]
CHANNELS_PATH = ROOT / "channels.yaml"
DATA_DIR = ROOT / "data"
FEEDS_JSON = DATA_DIR / "feeds.json"
VIDEOS_JSON = DATA_DIR / "videos.json"


def get_channel_url(channel: dict[str, Any]) -> str:
    url = (
        channel.get("url")
        or channel.get("feed_url")
        or channel.get("rss_url")
    )

    if url:
        return str(url).strip()

    channel_id = channel.get("channel_id")

    if channel_id:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={str(channel_id).strip()}"

    raise ValueError(f"Missing url/feed_url/rss_url/channel_id for channel: {channel}")


def extract_video_id(entry: Any) -> str | None:
    candidates: list[str] = []

    # feedparser usually exposes <yt:videoId> as entry.yt_videoid
    value = getattr(entry, "yt_videoid", None)
    if value:
        candidates.append(str(value))

    value = getattr(entry, "yt_videoId", None)
    if value:
        candidates.append(str(value))

    value = getattr(entry, "id", None)
    if value:
        candidates.append(str(value))

    value = getattr(entry, "link", None)
    if value:
        candidates.append(str(value))

    for text in candidates:
        if "yt:video:" in text:
            return text.split("yt:video:", 1)[1].strip()

        match = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", text)
        if match:
            return match.group(1)

        match = re.search(r"youtu\.be/([A-Za-z0-9_-]{6,})", text)
        if match:
            return match.group(1)

    return None


def load_channels() -> list[dict[str, Any]]:
    if not CHANNELS_PATH.exists():
        raise FileNotFoundError(f"Missing {CHANNELS_PATH}")

    data = yaml.safe_load(CHANNELS_PATH.read_text(encoding="utf-8")) or {}
    channels = data.get("channels", [])

    if not isinstance(channels, list):
        raise ValueError("channels.yaml must contain a list under key 'channels'.")

    return channels


def fetch_channel(channel: dict[str, Any]) -> list[dict[str, Any]]:
    url = get_channel_url(channel)

    feed = feedparser.parse(url)

    if getattr(feed, "bozo", False):
        print(f"  feed parse warning: {feed.bozo_exception}")

    print(f"  feed title: {feed.feed.get('title', 'N/A')}")
    print(f"  raw entries: {len(feed.entries)}")

    videos: list[dict[str, Any]] = []

    for entry in feed.entries:
        video_id = extract_video_id(entry)

        if not video_id:
            print(f"  skipped entry without video_id: {getattr(entry, 'title', '')}")
            continue

        video_url = f"https://www.youtube.com/watch?v={video_id}"

        media_group = getattr(entry, "media_group", None)
        thumbnail_url = ""

        try:
            thumbnails = media_group[0].get("media_thumbnail", []) if media_group else []
            if thumbnails:
                thumbnail_url = thumbnails[0].get("url", "")
        except Exception:
            thumbnail_url = ""

        video = {
            "video_id": video_id,
            "title": str(getattr(entry, "title", "")).strip(),
            "channel": str(channel.get("name", "")).strip(),
            "channel_category": str(channel.get("category", "")).strip(),
            "url": video_url,
            "published": str(getattr(entry, "published", "")).strip(),
            "updated": str(getattr(entry, "updated", "")).strip(),
            "summary": str(getattr(entry, "summary", "")).strip(),
            "thumbnail_url": thumbnail_url,
        }

        videos.append(video)

    return videos


def main() -> None:
    init_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    channels = load_channels()

    all_videos: list[dict[str, Any]] = []
    feed_snapshot: list[dict[str, Any]] = []

    for channel in channels:
        print(f"Fetching: {channel.get('name')}")

        try:
            videos = fetch_channel(channel)

            print(f"  videos: {len(videos)}")

            for video in videos:
                upsert_video(video)

            all_videos.extend(videos)

            feed_snapshot.append(
                {
                    "channel": channel,
                    "status": "ok",
                    "count": len(videos),
                }
            )

        except Exception as exc:
            print(f"  error: {exc}")

            feed_snapshot.append(
                {
                    "channel": channel,
                    "status": "error",
                    "error": str(exc),
                }
            )

    FEEDS_JSON.write_text(
        json.dumps(feed_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    VIDEOS_JSON.write_text(
        json.dumps(all_videos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Saved {len(all_videos)} videos.")


if __name__ == "__main__":
    main()
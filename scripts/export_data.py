from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from db import get_all_videos_joined, init_db


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
REPORTS_DIR = ROOT / "reports"

EXPORT_JSON = DATA_DIR / "export.json"
DOCS_DATA_JSON = DOCS_DIR / "data.json"
LATEST_REPORT = REPORTS_DIR / "latest.md"


def safe_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return []


def build_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    topic_counter: Counter[str] = Counter()
    signal_counter: Counter[str] = Counter()
    channel_counter: Counter[str] = Counter()
    importance_counter: Counter[str] = Counter()

    analyzed = 0

    for item in items:
        channel = item.get("channel") or "Unknown"
        channel_counter[channel] += 1

        analysis = item.get("analysis")

        if not analysis:
            continue

        analyzed += 1

        importance = analysis.get("importance") or "unknown"
        importance_counter[importance] += 1

        for topic in safe_list(analysis.get("topics")):
            topic_counter[str(topic)] += 1

        for signal in safe_list(analysis.get("signals")):
            signal_counter[str(signal)] += 1

    return {
        "total_videos": len(items),
        "analyzed_videos": analyzed,
        "channels": channel_counter.most_common(),
        "topics": topic_counter.most_common(),
        "signals": signal_counter.most_common(),
        "importance": importance_counter.most_common(),
    }


def build_report(items: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc).isoformat()

    analyzed_items = [
        item for item in items if item.get("analysis")
    ]

    high_priority = sorted(
        analyzed_items,
        key=lambda item: item["analysis"].get("watch_priority_score", 0),
        reverse=True,
    )[:10]

    lines = []
    lines.append("# LLM YouTube Landscape Tracker")
    lines.append("")
    lines.append(f"Generated at: `{now}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total videos: **{stats['total_videos']}**")
    lines.append(f"- Analyzed videos: **{stats['analyzed_videos']}**")
    lines.append("")
    lines.append("## Top Topics")
    lines.append("")

    for topic, count in stats["topics"][:15]:
        lines.append(f"- {topic}: {count}")

    lines.append("")
    lines.append("## Top Signals")
    lines.append("")

    for signal, count in stats["signals"][:15]:
        lines.append(f"- {signal}: {count}")

    lines.append("")
    lines.append("## High Priority Videos")
    lines.append("")

    for item in high_priority:
        analysis = item["analysis"]
        score = analysis.get("watch_priority_score", "")
        summary = analysis.get("one_sentence_summary", "")
        importance = analysis.get("importance", "")

        lines.append(f"### {item.get('title')}")
        lines.append("")
        lines.append(f"- Channel: {item.get('channel')}")
        lines.append(f"- Published: {item.get('published')}")
        lines.append(f"- Importance: {importance}")
        lines.append(f"- Score: {score}")
        lines.append(f"- URL: {item.get('url')}")
        lines.append(f"- Summary: {summary}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    init_db()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    items = get_all_videos_joined()
    stats = build_stats(items)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "items": items,
    }

    EXPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    DOCS_DATA_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = build_report(items, stats)

    LATEST_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print(f"Exported {len(items)} items.")
    print(f"Wrote {EXPORT_JSON}")
    print(f"Wrote {DOCS_DATA_JSON}")
    print(f"Wrote {LATEST_REPORT}")


if __name__ == "__main__":
    main()
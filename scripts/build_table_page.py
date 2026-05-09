import json
from pathlib import Path
import html
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "docs" / "data.json"
OUT_PATH = ROOT / "docs" / "table.html"


def esc(value):
    return html.escape(str(value or ""))


def is_analyzed(item):
    return item.get("analysis_status") == "ok" and isinstance(item.get("analysis"), dict)


def get_analysis(item):
    return item.get("analysis") if is_analyzed(item) else {}


def date_only(value):
    value = str(value or "")
    return value[:10] if len(value) >= 10 else value


def get_topics(item):
    a = get_analysis(item)
    topics = a.get("topics") or []
    if not topics:
        return ["pending transcript analysis"]
    return topics[:5]


def get_summary(item):
    a = get_analysis(item)
    if not a:
        return "No transcript-based analysis available yet."
    return a.get("one_sentence_summary") or a.get("detailed_summary") or "Transcript-based analysis available."


def get_speaker(item):
    a = get_analysis(item)
    return a.get("speaker") or "channel host"


def get_channel_angle(item):
    a = get_analysis(item)
    return a.get("channel_angle") or item.get("channel_category") or "Pending analysis."


def get_relation(item):
    a = get_analysis(item)
    return a.get("relation_to_other_channels") or "Pending transcript-based comparison."


def get_source(item):
    if is_analyzed(item):
        return "captions/transcript + LLM"

    status = item.get("transcript_status") or "unknown"
    if status == "error":
        return "captions unavailable"
    if status == "unknown":
        return "transcript not checked yet"
    return f"transcript status: {status}"


def get_score(item):
    a = get_analysis(item)
    if not a:
        return "unanalyzed"

    parts = []
    if a.get("watch_priority_score") is not None:
        parts.append(str(a.get("watch_priority_score")))
    if a.get("importance"):
        parts.append(a.get("importance"))
    return " / ".join(parts) if parts else "analyzed"


def get_evidence(item):
    a = get_analysis(item)
    evidence = a.get("evidence_snippets") or []
    if isinstance(evidence, list):
        return " | ".join(str(x) for x in evidence[:2])
    return ""


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    items = data["items"]
    generated_at = data.get("generated_at", "")

    total = len(items)
    analyzed = sum(1 for item in items if is_analyzed(item))
    transcript_ok = sum(1 for item in items if item.get("transcript_status") == "ok")
    channel_counts = Counter(item.get("channel") or "unknown" for item in items)

    rows = []

    for item in items:
        badge_class = "ok" if is_analyzed(item) else "pending"

        rows.append(f"""
        <tr>
          <td>{esc(date_only(item.get("published")))}</td>
          <td>{esc(item.get("channel"))}</td>
          <td>{esc(get_speaker(item))}</td>
          <td class="title">{esc(item.get("title"))}</td>
          <td>{"".join(f'<span class="tag">{esc(t)}</span>' for t in get_topics(item))}</td>
          <td>{esc(get_summary(item))}</td>
          <td>{esc(get_channel_angle(item))}</td>
          <td>{esc(get_relation(item))}</td>
          <td><span class="badge {badge_class}">{esc(get_source(item))}</span></td>
          <td>{esc(get_score(item))}</td>
          <td>{esc(get_evidence(item))}</td>
          <td><a href="{esc(item.get("url"))}" target="_blank" rel="noopener noreferrer">Watch</a></td>
        </tr>
        """)

    channel_line = ", ".join(f"{esc(k)}: {v}" for k, v in channel_counts.most_common())

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LLM YouTube Landscape Tracker — Concise Table</title>
  <style>
    body {{
      margin: 0;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7fb;
      color: #111827;
    }}

    header {{
      padding: 36px 28px;
      background: linear-gradient(135deg, #111827, #312e81);
      color: white;
    }}

    header h1 {{
      margin: 0 0 10px;
      font-size: 42px;
      letter-spacing: -0.04em;
    }}

    header p {{
      margin: 0;
      max-width: 1100px;
      color: #d1d5db;
      line-height: 1.6;
      font-size: 17px;
    }}

    main {{
      max-width: 1800px;
      margin: 0 auto;
      padding: 24px;
    }}

    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}

    .metric {{
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 16px;
      padding: 18px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
    }}

    .metric span {{
      display: block;
      color: #6b7280;
      font-size: 13px;
      margin-bottom: 6px;
    }}

    .metric strong {{
      font-size: 30px;
    }}

    .note {{
      background: #fffbeb;
      border: 1px solid #fde68a;
      color: #92400e;
      padding: 14px 16px;
      border-radius: 14px;
      margin-bottom: 20px;
      line-height: 1.6;
    }}

    .channels {{
      color: #6b7280;
      margin-bottom: 20px;
      line-height: 1.6;
    }}

    .table-wrap {{
      overflow-x: auto;
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 18px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
    }}

    table {{
      width: 100%;
      min-width: 1700px;
      border-collapse: collapse;
    }}

    th,
    td {{
      padding: 12px 14px;
      border-bottom: 1px solid #e5e7eb;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
      line-height: 1.45;
    }}

    th {{
      background: #f9fafb;
      color: #374151;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      position: sticky;
      top: 0;
      z-index: 2;
    }}

    .title {{
      font-weight: 800;
      max-width: 260px;
    }}

    .tag {{
      display: inline-block;
      margin: 2px;
      padding: 4px 8px;
      border-radius: 999px;
      background: #eef2ff;
      color: #3730a3;
      font-size: 12px;
      white-space: nowrap;
    }}

    .badge {{
      display: inline-block;
      padding: 5px 9px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }}

    .badge.ok {{
      background: #dcfce7;
      color: #166534;
    }}

    .badge.pending {{
      background: #fee2e2;
      color: #991b1b;
    }}

    a {{
      color: #2563eb;
      text-decoration: none;
      font-weight: 800;
    }}

    a:hover {{
      text-decoration: underline;
    }}

    @media (max-width: 900px) {{
      .metrics {{
        grid-template-columns: 1fr;
      }}

      header h1 {{
        font-size: 30px;
      }}

      main {{
        padding: 14px;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>LLM YouTube Landscape Tracker — Concise Table</h1>
    <p>
      A concise table categorising LLM-related YouTube videos by speaker, topic, transcript-grounded summary,
      source status, and relationship to other tracked AI channels.
    </p>
  </header>

  <main>
    <section class="metrics">
      <div class="metric">
        <span>Total videos</span>
        <strong>{total}</strong>
      </div>
      <div class="metric">
        <span>Transcript OK</span>
        <strong>{transcript_ok}</strong>
      </div>
      <div class="metric">
        <span>Transcript-based analyses</span>
        <strong>{analyzed}</strong>
      </div>
      <div class="metric">
        <span>Last generated</span>
        <strong style="font-size: 16px;">{esc(str(generated_at)[:19])}</strong>
      </div>
    </section>

    <div class="note">
      Methodology: Videos are collected from YouTube RSS feeds. LLM summaries are shown only for rows with available captions/transcripts and successful analysis.
      Rows without reliable transcript-based analysis are marked as pending or unavailable instead of being summarized from titles or thumbnails alone.
    </div>

    <div class="channels">
      <strong>Channel coverage:</strong> {channel_line}
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Channel</th>
            <th>Speaker</th>
            <th>Video</th>
            <th>Topics</th>
            <th>Transcript-grounded summary</th>
            <th>Channel angle</th>
            <th>Relation to other channels</th>
            <th>Source</th>
            <th>Score</th>
            <th>Evidence</th>
            <th>Link</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </div>
  </main>
</body>
</html>
"""

    OUT_PATH.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"Total={total}, transcript_ok={transcript_ok}, analyzed={analyzed}")


if __name__ == "__main__":
    main()
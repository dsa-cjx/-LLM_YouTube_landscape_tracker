from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from db import get_videos_ready_for_analysis, init_db, upsert_analysis
from llm_client import ask_llm


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TAXONOMY_PATH = ROOT / "taxonomy.yaml"
DATA_DIR = ROOT / "data"
ANALYSES_JSON = DATA_DIR / "analyses.json"

load_dotenv(ENV_PATH)


SYSTEM_PROMPT = """
You are an expert AI industry analyst.

Analyze YouTube video transcripts about AI, foundation models, agents,
RAG, AI infrastructure, products, research, and the AI market.

CRITICAL OUTPUT RULES:
- Return exactly one valid JSON object.
- Do not wrap the JSON in markdown.
- Do not use code fences.
- Do not include explanations.
- Do not include analysis notes.
- Do not include chain-of-thought.
- Do not include reasoning.
- Do not include "Thinking".
- Do not include "Thinking Process".
- The first non-whitespace character of your response must be "{".
- The last non-whitespace character of your response must be "}".
""".strip()


def load_taxonomy() -> dict[str, Any]:
    if not TAXONOMY_PATH.exists():
        return {}

    return yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8")) or {}


def truncate_text(text: str, max_chars: int = 28000) -> str:
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    head = text[: int(max_chars * 0.7)]
    tail = text[-int(max_chars * 0.3) :]

    return head + "\n\n[... middle truncated ...]\n\n" + tail


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()

    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    return cleaned.strip()


def extract_json(text: str) -> dict[str, Any]:
    """
    Robustly extract one JSON object from model output.

    Handles:
    - pure JSON
    - ```json fenced JSON
    - accidental leading text
    - accidental trailing text
    - model 'Thinking...' preambles
    - braces inside JSON strings
    """
    if not text or not text.strip():
        raise ValueError("Model returned empty output.")

    cleaned = strip_code_fences(text)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"Model returned JSON but not an object: {type(parsed).__name__}")
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    if start < 0:
        raise ValueError(f"Could not find JSON object in model output: {text[:1000]}")

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(cleaned)):
        ch = cleaned[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1

            if depth == 0:
                candidate = cleaned[start : i + 1]

                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "Found JSON-like object but could not parse it: "
                        f"{exc}. Preview: {candidate[:1000]}"
                    ) from exc

                if not isinstance(parsed, dict):
                    raise ValueError(
                        f"Extracted JSON is not an object: {type(parsed).__name__}"
                    )

                return parsed

    raise ValueError(f"Could not parse JSON from model output: {text[:1000]}")


def safe_list(value: Any) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        if not value.strip():
            return []
        return [value]

    return []


def normalize_analysis(data: dict[str, Any], video: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("video_id", video.get("video_id"))
    data.setdefault("title", video.get("title"))
    data.setdefault("one_sentence_summary", "")
    data.setdefault("detailed_summary", "")
    data.setdefault("topics", [])
    data.setdefault("signals", [])
    data.setdefault("companies_or_projects", [])
    data.setdefault("models_or_tools", [])
    data.setdefault("people", [])
    data.setdefault("importance", "medium")
    data.setdefault("importance_reason", "")
    data.setdefault("market_impact", "")
    data.setdefault("technical_takeaways", [])
    data.setdefault("product_takeaways", [])
    data.setdefault("recommended_audience", [])
    data.setdefault("notable_quotes_or_claims", [])
    data.setdefault("watch_priority_score", 5)

    data["video_id"] = video.get("video_id")
    data["title"] = data.get("title") or video.get("title") or ""

    importance = str(data.get("importance") or "medium").lower().strip()
    if importance not in {"low", "medium", "high"}:
        importance = "medium"
    data["importance"] = importance

    try:
        score = int(data.get("watch_priority_score", 5))
    except Exception:
        score = 5

    data["watch_priority_score"] = max(1, min(10, score))

    list_fields = [
        "topics",
        "signals",
        "companies_or_projects",
        "models_or_tools",
        "people",
        "technical_takeaways",
        "product_takeaways",
        "recommended_audience",
        "notable_quotes_or_claims",
    ]

    for field in list_fields:
        data[field] = safe_list(data.get(field))

    text_fields = [
        "title",
        "one_sentence_summary",
        "detailed_summary",
        "importance_reason",
        "market_impact",
    ]

    for field in text_fields:
        if data.get(field) is None:
            data[field] = ""
        elif not isinstance(data.get(field), str):
            data[field] = str(data.get(field))

    return data


def build_prompt(video: dict[str, Any], taxonomy: dict[str, Any]) -> str:
    transcript = truncate_text(video.get("transcript", "") or "")

    topics = taxonomy.get("topics", [])
    signals = taxonomy.get("signals", [])
    importance_levels = taxonomy.get("importance_levels", ["low", "medium", "high"])

    return f"""
Analyze the following YouTube video transcript.

CRITICAL OUTPUT RULES:
- Return exactly one valid JSON object.
- Return JSON only.
- Do not output markdown.
- Do not output code fences.
- Do not output explanations.
- Do not output chain-of-thought.
- Do not output reasoning.
- Do not output "Thinking".
- Do not output "Thinking Process".
- Your entire response must start with "{{" and end with "}}".

Video metadata:
- video_id: {video.get("video_id")}
- title: {video.get("title")}
- channel: {video.get("channel")}
- channel_category: {video.get("channel_category")}
- url: {video.get("url")}
- published: {video.get("published")}

Allowed topics:
{json.dumps(topics, ensure_ascii=False)}

Allowed signals:
{json.dumps(signals, ensure_ascii=False)}

Allowed importance levels:
{json.dumps(importance_levels, ensure_ascii=False)}

Return exactly one valid JSON object with this schema:

{{
  "video_id": "string",
  "title": "string",
  "one_sentence_summary": "string",
  "detailed_summary": "string",
  "topics": ["string"],
  "signals": ["string"],
  "companies_or_projects": ["string"],
  "models_or_tools": ["string"],
  "people": ["string"],
  "importance": "low | medium | high",
  "importance_reason": "string",
  "market_impact": "string",
  "technical_takeaways": ["string"],
  "product_takeaways": ["string"],
  "recommended_audience": ["researcher", "engineer", "founder", "investor", "product_manager", "student"],
  "notable_quotes_or_claims": ["string"],
  "watch_priority_score": 1
}}

Rules:
- Return only JSON.
- "watch_priority_score" must be an integer from 1 to 10.
- Use only topics from allowed topics when possible.
- Use only signals from allowed signals when possible.
- Use only one of these importance values: low, medium, high.
- If unsure, use empty arrays.
- Do not invent facts that are not supported by the transcript.
- Write the summary in Chinese.
- Keep company/model/project names in their original English form.

Transcript:
\"\"\"
{transcript}
\"\"\"
""".strip()


def analyze_one(video: dict[str, Any], taxonomy: dict[str, Any]) -> dict[str, Any]:
    prompt = build_prompt(video, taxonomy)

    output = ask_llm(
        prompt=prompt,
        system=SYSTEM_PROMPT,
        temperature=0.0,
        max_tokens=1800,
    )

    data = extract_json(output)
    data = normalize_analysis(data, video)

    return data


def main() -> None:
    init_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    limit = int(os.getenv("MAX_ANALYSES_PER_RUN", "12"))
    taxonomy = load_taxonomy()

    videos = get_videos_ready_for_analysis(limit=limit)

    print(f"Videos ready for analysis: {len(videos)}", flush=True)

    results = []

    for idx, video in enumerate(videos, start=1):
        video_id = video["video_id"]
        title = video.get("title", "")

        print(f"[{idx}/{len(videos)}] Analyzing: {video_id} | {title}", flush=True)

        try:
            analysis = analyze_one(video, taxonomy)

            upsert_analysis(
                video_id=video_id,
                analysis_json=analysis,
                status="ok",
            )

            print(
                f"  ok: priority={analysis.get('watch_priority_score')} "
                f"importance={analysis.get('importance')}",
                flush=True,
            )

            results.append(
                {
                    "video_id": video_id,
                    "status": "ok",
                    "analysis": analysis,
                }
            )

        except KeyboardInterrupt:
            print("\nInterrupted by user.", flush=True)
            raise

        except Exception as exc:
            error_message = str(exc)
            print(f"  error: {error_message}", flush=True)

            upsert_analysis(
                video_id=video_id,
                analysis_json=None,
                status="error",
                error=error_message,
            )

            results.append(
                {
                    "video_id": video_id,
                    "status": "error",
                    "error": error_message,
                }
            )

    ANALYSES_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Analysis done.", flush=True)


if __name__ == "__main__":
    main()
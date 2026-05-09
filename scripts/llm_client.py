from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

load_dotenv(ENV_PATH)


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)

    if value is None:
        return default

    value = value.strip()

    if not value:
        return default

    return value


def get_env_int(name: str, default: int) -> int:
    value = get_env(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def get_env_float(name: str, default: float) -> float:
    value = get_env(name)

    if value is None:
        return default

    try:
        return float(value)
    except ValueError:
        return default


def get_llm_client() -> tuple[OpenAI, str]:
    provider = get_env("LLM_PROVIDER", "poe").lower()

    if provider != "poe":
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

    api_key = get_env("POE_API_KEY")
    base_url = get_env("POE_BASE_URL", "https://api.poe.com/v1")

    # Default to GPT-4o mini instead of Qwen.
    # If Poe says model/bot not found, try changing this in .env to Poe's exact bot name.
    model = get_env("POE_MODEL", "GPT-4o-Mini")

    timeout_seconds = get_env_float("LLM_TIMEOUT_SECONDS", 90.0)
    max_retries = get_env_int("LLM_MAX_RETRIES", 1)

    if not api_key:
        raise RuntimeError(
            "Missing POE_API_KEY. Please set it in .env or environment variables."
        )

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )

    return client, model


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()

    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    return cleaned.strip()


def extract_json_text(text: str) -> str | None:
    """
    Return the first complete JSON object text if one exists.

    Uses brace matching so it is safer than first-{ to last-}.
    """
    cleaned = text.strip()
    start = cleaned.find("{")

    if start < 0:
        return None

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
                return cleaned[start : i + 1].strip()

    return None


def clean_model_output(text: str) -> str:
    """
    Cleans model output.

    Handles:
    - Markdown code fences
    - Accidental preamble
    - Accidental trailing text
    - Visible reasoning/thinking text from non-chat models
    """

    if not text:
        return ""

    cleaned = strip_code_fences(text)

    json_text = extract_json_text(cleaned)
    if json_text:
        return json_text

    markers = [
        "\nFinal answer:",
        "\nFinal Answer:",
        "\nFINAL ANSWER:",
        "\nAnswer:",
        "\nANSWER:",
        "\nOutput:",
        "\nOUTPUT:",
        "\nResult:",
        "\nRESULT:",
    ]

    for marker in markers:
        idx = cleaned.rfind(marker)
        if idx >= 0:
            return cleaned[idx + len(marker) :].strip()

    lines = [line.rstrip() for line in cleaned.splitlines() if line.strip()]

    filtered_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        if stripped.startswith(">"):
            continue

        if lower in {
            "thinking...",
            "thinking",
            "thinking process:",
            "reasoning:",
            "analysis:",
        }:
            continue

        if lower.startswith("thinking process"):
            continue

        filtered_lines.append(line)

    if filtered_lines:
        return "\n".join(filtered_lines).strip()

    return cleaned


def chat_completion(
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    client, model = get_llm_client()

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    timeout_seconds = get_env_float("LLM_TIMEOUT_SECONDS", 90.0)

    try:
        response = client.chat.completions.create(**kwargs)

    except APITimeoutError as exc:
        raise RuntimeError(
            f"LLM request timed out after about {timeout_seconds} seconds. "
            f"Model={model}. Try increasing LLM_TIMEOUT_SECONDS or use a faster Poe model."
        ) from exc

    except APIConnectionError as exc:
        raise RuntimeError(
            f"LLM connection error. Model={model}. "
            "Check network, Poe API status, POE_API_KEY, and POE_BASE_URL."
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            f"LLM request failed. Model={model}. Error={exc}"
        ) from exc

    if not response.choices:
        raise RuntimeError(f"LLM returned no choices. Model={model}")

    content = response.choices[0].message.content or ""
    cleaned = clean_model_output(content)

    if not cleaned:
        raise RuntimeError(
            f"LLM returned empty content after cleaning. Model={model}. "
            f"Raw content preview: {content[:500]}"
        )

    return cleaned


def ask_llm(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    messages: list[dict[str, str]] = []

    if system:
        messages.append(
            {
                "role": "system",
                "content": system,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    return chat_completion(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
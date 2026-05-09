from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from llm_client import ask_llm, get_llm_client


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def main() -> None:
    load_dotenv(ENV_PATH)

    print("Project root:", ROOT)
    print("Env path:", ENV_PATH)
    print("Env file exists:", ENV_PATH.exists())
    print("POE_API_KEY loaded:", bool(os.getenv("POE_API_KEY")))

    client, model = get_llm_client()

    print("Poe API client created:", client is not None)
    print("Model:", model)

    result = ask_llm(
        prompt="Reply exactly: Poe works",
        temperature=0,
        max_tokens=200,
    )

    print("Response:")
    print(result)

    if result.strip() == "Poe works":
        print("Test passed.")
    else:
        print("Poe responded, but not exactly. This is acceptable for some reasoning models.")


if __name__ == "__main__":
    main()
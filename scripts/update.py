from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_step(name: str, script: str) -> None:
    print("")
    print("=" * 80)
    print(f"STEP: {name}")
    print("=" * 80)

    cmd = [sys.executable, str(ROOT / "scripts" / script)]

    subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
    )


def main() -> None:
    run_step("Fetch YouTube feeds", "fetch_feeds.py")
    run_step("Fetch transcripts", "fetch_transcripts.py")
    run_step("Analyze videos with Poe", "analyze_video.py")
    run_step("Build static site", "build_site.py")

    print("")
    print("All done.")


if __name__ == "__main__":
    main()
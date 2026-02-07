"""Update README.md (latest only) and append checkin_log.md.

This script is intentionally small and deterministic.

Inputs:
  - run_artifacts/result.json  (written by attendance_bot.py)
Outputs:
  - README.md updated (Latest only)
  - checkin_log.md appended

Usage:
  python scripts/update_repo_files.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "run_artifacts"
RESULT_PATH = ART / "result.json"
README = ROOT / "README.md"
LOG = ROOT / "checkin_log.md"


def _read_result() -> dict:
    if not RESULT_PATH.exists():
        raise SystemExit(f"Missing {RESULT_PATH}. Run attendance_bot.py first.")
    return json.loads(RESULT_PATH.read_text(encoding="utf-8"))


def _ensure_log_header() -> None:
    if LOG.exists() and LOG.read_text(encoding="utf-8").strip():
        return
    LOG.write_text("# Evergreen 출석 로그\n\n", encoding="utf-8")


def main() -> None:
    r = _read_result()
    base_url = r.get("base_url", "")
    attendance_url = r.get("attendance_url", "")
    ts = r.get("timestamp_kst", "")
    result = r.get("result", "failed")

    # README: latest only
    readme_text = (
        "# Evergreen 출석 자동화\n\n"
        "매일 자동으로 에버그린 출석을 수행합니다.\n\n"
        "## Latest Check-in\n\n"
        f"- **Time(KST):** {ts}\n"
        f"- **Result:** {result}\n"
        f"- **Attendance URL:** {attendance_url}\n"
        f"- **Base URL:** {base_url}\n"
    )
    README.write_text(readme_text, encoding="utf-8")

    # log append
    _ensure_log_header()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"- {ts} - {result} - {attendance_url}\n")


if __name__ == "__main__":
    main()

"""Read and persist fixed NAO scenarios and local training sessions.

scenarios.json contains predefined reference labels. sessions.json stores
local prototype progress and is replaced via a temporary file on save.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_FILE = ROOT / "data" / "scenarios.json"

with open(SCENARIOS_FILE, "r", encoding="utf-8") as file:
    scenarios_db = json.load(file)
SESSIONS_FILE = ROOT / "data" / "sessions.json"


def load_sessions():
    """Read previous sessions, or start with an empty dictionary."""
    if not SESSIONS_FILE.exists():
        return {}

    with open(SESSIONS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


sessions = load_sessions()


def save_sessions():
    """Persist all sessions using a temporary-file replacement."""
    SESSIONS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = SESSIONS_FILE.with_suffix(".json.tmp")

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(
            sessions,
            file,
            indent=4,
            ensure_ascii=False
        )

    temp_file.replace(SESSIONS_FILE)

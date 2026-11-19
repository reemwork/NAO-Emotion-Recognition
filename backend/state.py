
"""Load and persist NAO training session data.

Scenarios are loaded from scenarios.json.
Session progress, verbal responses, and facial observations
are stored in sessions.json and restored on backend startup.
"""

import json
from pathlib import Path
from threading import Lock


# -------------------- File Paths --------------------

ROOT = Path(__file__).resolve().parent.parent

SCENARIOS_FILE = ROOT / "data" / "scenarios.json"
SESSIONS_FILE = ROOT / "data" / "sessions.json"

# Protect concurrent file writes within one Python process.
_save_lock = Lock()


# -------------------- Scenario Loading --------------------

with open(SCENARIOS_FILE, "r", encoding="utf-8") as file:
    scenarios_db = json.load(file)


# -------------------- Session Loading --------------------

def load_sessions():
    """Restore saved sessions or return an empty dictionary."""
    if not SESSIONS_FILE.exists():
        return {}

    with open(SESSIONS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


sessions = load_sessions()


# -------------------- Session Saving --------------------

def save_sessions():
    """Save sessions with a lock and atomic file replacement.

    The lock prevents simultaneous writes within one process.
    The temporary file reduces the risk of partial JSON files.
    """
    with _save_lock:
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

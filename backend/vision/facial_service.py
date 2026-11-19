
"""Facial analysis and observation storage for NAO sessions.

Runs ResMaskingNet independently of verbal answer evaluation.
Prevents duplicate analysis of the same frame within one process.
"""

from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from fastapi import HTTPException

import backend


_facial_lock = RLock()


def _backend():
    """Access the configured application and mockable classifier."""
    return backend.app


def _observations(session, scenario_id):
    """Return the facial observations list for a scenario."""
    return session.setdefault(
        "facial_observations", {}
    ).setdefault(str(scenario_id), [])


def _existing_observation(session, scenario_id, image_file):
    """Find a real observation already saved for this frame."""
    return next(
        (
            item for item in _observations(session, scenario_id)
            if item.get("source") == "resmaskingnet"
            and item.get("image_file") == image_file
        ),
        None
    )


def _frame_path(image_file):
    """Resolve a stored frame securely within the project folder."""
    root = _backend().ROOT.resolve()
    path = (root / image_file).resolve()

    if not path.is_relative_to(root):
        raise HTTPException(
            status_code=400,
            detail="Invalid stored frame path."
        )

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored frame not found."
        )

    return path


def _store_observation(session, scenario_id, image_file, prediction):
    """Save a real ResMaskingNet prediction."""
    observation = {
        "observation_id": str(uuid4()),
        "dominant_emotion": prediction["dominant_emotion"],
        "confidence": prediction["confidence"],
        "image_file": image_file,
        "source": "resmaskingnet",
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }

    _observations(session, scenario_id).append(observation)

    session.setdefault(
        "camera_analysis_status", {}
    )[image_file] = "Analyzed"

    _backend().save_sessions()

    return observation


def _run_facial_analysis(session, scenario_id, image_file):
    """Run inference once for each image within one Python process."""
    with _facial_lock:
        existing = _existing_observation(
            session, scenario_id, image_file
        )

        if existing is not None:
            return existing, True

        prediction = _backend().classify_facial_frame(
            _frame_path(image_file)
        )

        if prediction is None:
            return None, False

        observation = _store_observation(
            session,
            scenario_id,
            image_file,
            prediction
        )

        return observation, False

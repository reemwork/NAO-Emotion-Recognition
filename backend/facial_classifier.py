"""Local ResMaskingNet facial-expression inference for saved session frames.

This module is intentionally lazy: backend startup and mocked tests do not
need OpenCV, RMN, or model weights. The model runs on the PC, not on NAO.
"""

import math
from functools import lru_cache

LABELS = {
    "angry": "Angry",
    "disgust": "Disgust",
    "fear": "Fear",
    "happy": "Happy",
    "sad": "Sad",
    "surprise": "Surprise",
    "neutral": "Neutral",
}


class FacialInferenceError(RuntimeError):
    """Missing dependency, unavailable model, or invalid model output."""


@lru_cache(maxsize=1)
def _get_model():
    try:
        from rmn import RMN
    except ImportError as error:
        raise FacialInferenceError(
            "Local ResMaskingNet is not installed. Run: python -m pip install rmn"
        ) from error

    try:
        return RMN()
    except Exception as error:
        raise FacialInferenceError(
            "Could not load local ResMaskingNet. Check model weights and installation."
        ) from error


def normalize_detections(detections):
    """Return a single face's label/confidence, or None when no face was found.

    RMN returns one dictionary per detected face with emo_label and emo_proba.
    We do not arbitrarily select one person if several faces are visible.
    """
    if not isinstance(detections, (list, tuple)):
        raise FacialInferenceError("Invalid ResMaskingNet detection format.")
    if not detections:
        return None
    if len(detections) != 1:
        raise FacialInferenceError(
            "Multiple faces detected; a single participant face is required."
        )

    face = detections[0]
    if not isinstance(face, dict):
        raise FacialInferenceError("Invalid ResMaskingNet face result.")

    raw_label = str(face.get("emo_label", "")).strip().lower()
    if raw_label not in LABELS:
        raise FacialInferenceError(
            "ResMaskingNet returned an unknown facial-expression label."
        )

    try:
        confidence = float(face["emo_proba"])
    except (KeyError, TypeError, ValueError) as error:
        raise FacialInferenceError("Invalid facial-expression confidence.") from error

    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise FacialInferenceError(
            "Facial-expression confidence must be between 0 and 1."
        )

    return {
        "dominant_emotion": LABELS[raw_label],
        "confidence": confidence,
    }


def classify_facial_frame(image_path):
    """Classify the face in a locally stored JPEG/PNG using ResMaskingNet."""
    try:
        import cv2
    except ImportError as error:
        raise FacialInferenceError(
            "OpenCV is required. Run: python -m pip install opencv-python"
        ) from error

    frame = cv2.imread(str(image_path))
    if frame is None:
        raise FacialInferenceError("Saved facial frame could not be opened.")

    try:
        detections = _get_model().detect_emotion_for_single_frame(frame)
    except FacialInferenceError:
        raise
    except Exception as error:
        raise FacialInferenceError("Local ResMaskingNet inference failed.") from error

    return normalize_detections(detections)

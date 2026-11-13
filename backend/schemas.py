"""Shared FastAPI request schemas for sessions, audio, and vision."""

from typing import Literal
from pydantic import BaseModel, Field


class ChildResponse(BaseModel):
    """Text captured or transcribed for one session's scenario; sent to Qwen."""
    session_id: str
    scenario_id: int
    spoken_text: str


class ScenarioEvent(BaseModel):
    """Identifies the active scenario to start, complete or evaluate."""
    session_id: str
    scenario_id: int


class SessionEnd(BaseModel):
    """Identifies the session that the caller wants to close."""
    session_id: str


class ScenarioRecovery(BaseModel):
    """Explains why an active scenario must be retried or skipped."""
    session_id: str
    scenario_id: int
    # "retry" keeps the scenario active; "skip" resolves it without an answer.
    action: Literal["retry", "skip"]
    reason: Literal[
        "no_response", "no_speech_recognized",
        "transcription_failed", "processing_failed"
    ]


class FacialResult(BaseModel):
    """Validated mock/manual facial observation; confidence must be 0..1."""
    session_id: str
    scenario_id: int
    # Facial labels have seven classes; verbal scenarios currently use four.
    dominant_emotion: Literal[
        "Happy", "Sad", "Angry", "Neutral",
        "Fear", "Surprise", "Disgust"
    ]
    confidence: float = Field(ge=0, le=1)

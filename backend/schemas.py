"""Shared FastAPI request schemas for sessions, audio, and vision."""

from typing import Literal
from pydantic import BaseModel, Field


class ChildResponse(BaseModel):
    session_id: str
    scenario_id: int
    spoken_text: str


class ScenarioEvent(BaseModel):
    session_id: str
    scenario_id: int


class SessionEnd(BaseModel):
    session_id: str


class ScenarioRecovery(BaseModel):
    session_id: str
    scenario_id: int
    action: Literal["retry", "skip"]
    reason: Literal[
        "no_response", "no_speech_recognized",
        "transcription_failed", "processing_failed"
    ]


class FacialResult(BaseModel):
    session_id: str
    scenario_id: int
    dominant_emotion: Literal[
        "Happy", "Sad", "Angry", "Neutral",
        "Fear", "Surprise", "Disgust"
    ]
    confidence: float = Field(ge=0, le=1)

"""Offline backend workflow tests.

Run from the repository root:
    python -m unittest tests.test_backend_workflow -v

Whisper/Qwen and network/NAO transfers are mocked. No real microphone,
camera, robot, local Ollama model, or participant files are needed.
"""
import asyncio
import importlib
import io
import tempfile
import types
import sys
import unittest
from pathlib import Path
from unittest import mock

import requests
from fastapi import HTTPException, UploadFile
from PIL import Image

# Avoid loading Whisper weights during automated backend tests.
fake_stt = types.ModuleType("backend.transcribe_audio")
fake_stt.model = mock.Mock()
fake_stt.transcribe_audio = mock.Mock(return_value="Mock transcript")
with mock.patch.dict(sys.modules, {"backend.transcribe_audio": fake_stt}):
    backend = importlib.import_module("backend.app")

from backend import nao_transfer


def sample_image():
    """Create a small in-memory JPEG so camera tests do not need NAO."""
    stream = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(stream, format="JPEG")
    stream.seek(0)
    return UploadFile(filename="face.jpg", file=stream)


def sample_audio():
    """Create a lightweight fake WAV upload; Whisper is mocked in these tests."""
    return UploadFile(
        filename="recording.wav",
        file=io.BytesIO(b"RIFF" + b"0" * 44)
    )


class BackendWorkflowTests(unittest.TestCase):
    """Integration-style tests using mocked model/robot interfaces."""
    def setUp(self):
        """Isolate session state/files in a fresh temporary directory for each test."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch_root = mock.patch.object(
            backend, "ROOT", Path(self.temp.name)
        )
        self.patch_save = mock.patch.object(backend, "save_sessions")
        self.patch_sessions = mock.patch.dict(backend.sessions, {}, clear=True)
        for patcher in (self.patch_root, self.patch_save, self.patch_sessions):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.session_id = backend.start_session()["session_id"]

    def event(self, scenario_id=1):
        """Build a scenario request referring to the current test session."""
        return backend.ScenarioEvent(
            session_id=self.session_id, scenario_id=scenario_id
        )

    def start(self, scenario_id=1):
        """Start a scenario through the real backend handler."""
        return backend.start_scenario(self.event(scenario_id))

    def submit(self, scenario_id=1, emotion="Happy"):
        """Mock Qwen to submit a predictable answer without running Ollama."""
        with mock.patch.object(
            backend, "classify_emotion", return_value=emotion
        ):
            return backend.submit_response(
                backend.ChildResponse(
                    session_id=self.session_id,
                    scenario_id=scenario_id,
                    spoken_text="He looks happy because he is smiling."
                )
            )

    def recovery(self, action="skip", reason="no_response", scenario_id=1):
        """Build and issue a retry/skip request for a test scenario."""
        return backend.recover_scenario(
            backend.ScenarioRecovery(
                session_id=self.session_id,
                scenario_id=scenario_id,
                action=action,
                reason=reason
            )
        )

    def test_two_scenarios_in_one_session(self):
        """Ensure multiple scenarios share one session and correctly count answers."""
        self.start(1)
        self.submit(1)
        backend.complete_scenario(self.event(1))
        self.start(2)
        self.submit(2, emotion="Sad")
        backend.complete_scenario(self.event(2))
        result = backend.get_session_results(self.session_id)
        self.assertEqual(result["total_responses"], 2)
        self.assertEqual(result["summary"]["correct"], 2)
        self.assertIsNone(result["active_scenario_id"])
        self.assertEqual(result["scenario_progress"]["2"]["status"], "completed")

    def test_no_response_is_skipped_not_unclear(self):
        """Skipping due to silence must not create a false 'Unclear' answer."""
        self.start(1)
        skipped = self.recovery(action="skip", reason="no_response")
        self.assertEqual(skipped["scenario_status"], "skipped")
        result = backend.get_session_results(self.session_id)
        self.assertEqual(result["total_responses"], 0)
        self.assertEqual(result["skipped_scenarios"], 1)
        self.assertEqual(result["summary"]["unclear"], 0)
        self.start(2)  # A skipped question must not block the next one.

    def test_retry_keeps_scenario_open(self):
        """Confirm retry does not resolve the scenario until an answer is submitted."""
        self.start()
        result = self.recovery(
            action="retry", reason="no_speech_recognized"
        )
        self.assertEqual(result["scenario_status"], "in_progress")
        self.submit()
        self.assertEqual(backend.complete_scenario(self.event())["scenario_status"],
                         "completed")

    def test_processing_failure_is_logged_and_retry_is_possible(self):
        """Qwen downtime is logged and does not prevent a later retry."""
        self.start()
        with mock.patch.object(
            backend, "classify_emotion",
            side_effect=requests.exceptions.Timeout("Ollama unavailable")
        ):
            with self.assertRaises(HTTPException) as error:
                backend.submit_response(
                    backend.ChildResponse(
                        session_id=self.session_id,
                        scenario_id=1, spoken_text="He looks happy"
                    )
                )
        self.assertEqual(error.exception.status_code, 503)
        progress = backend.sessions[self.session_id]["scenario_progress"]["1"]
        self.assertEqual(progress["issues"][0]["reason"], "processing_failed")
        self.assertEqual(backend.get_session_results(
            self.session_id)["total_responses"], 0)
        self.submit()
        backend.complete_scenario(self.event())

    def test_no_speech_recognized_is_logged(self):
        """An empty Whisper transcript returns 422 and records the issue."""
        self.start()
        with mock.patch.object(
            backend.whisper_model, "transcribe",
            return_value={"text": "  "}
        ):
            with self.assertRaises(HTTPException) as error:
                backend.evaluate_audio(
                    self.session_id, 1, sample_audio()
                )
        self.assertEqual(error.exception.status_code, 422)
        state = backend.sessions[self.session_id]["scenario_progress"]["1"]
        self.assertEqual(state["issues"][0]["reason"], "no_speech_recognized")
        self.assertEqual(state["status"], "in_progress")

    def test_transcription_exception_is_logged(self):
        """A Whisper exception returns 500 and leaves a recoverable scenario."""
        self.start()
        with mock.patch.object(
            backend.whisper_model, "transcribe",
            side_effect=RuntimeError("mock STT failure")
        ):
            with self.assertRaises(HTTPException) as error:
                backend.evaluate_audio(self.session_id, 1, sample_audio())
        self.assertEqual(error.exception.status_code, 500)
        state = backend.sessions[self.session_id]["scenario_progress"]["1"]
        self.assertEqual(state["issues"][0]["reason"], "transcription_failed")

    def test_camera_first_then_audio(self):
        """An image uploaded before the response must still link to that response."""
        self.start()
        frame = asyncio.run(
            backend.upload_session_frame(
                session_id=self.session_id,
                scenario_id=1,
                frame=sample_image()
            )
        )
        self.assertFalse(frame["linked_to_response"])

        with (
            mock.patch.object(
                backend.whisper_model, "transcribe",
                return_value={"text": "He looks happy"}
            ),
            mock.patch.object(
                backend, "classify_emotion", return_value="Happy"
            )
        ):
            audio = backend.evaluate_audio(
                self.session_id, 1, sample_audio()
            )

        self.assertEqual(audio["saved_result"]["evaluation"], "Correct")
        self.assertEqual(
            audio["saved_result"]["face_image_file"], frame["image_file"]
        )
        self.assertIn("audio_file", audio["saved_result"])

    def test_audio_first_then_camera(self):
        """An image uploaded after the response must also link correctly."""
        self.start()
        with (
            mock.patch.object(
                backend.whisper_model, "transcribe",
                return_value={"text": "He looks happy"}
            ),
            mock.patch.object(
                backend, "classify_emotion", return_value="Happy"
            )
        ):
            backend.evaluate_audio(self.session_id, 1, sample_audio())

        frame = asyncio.run(
            backend.upload_session_frame(
                session_id=self.session_id, scenario_id=1,
                frame=sample_image()
            )
        )
        self.assertTrue(frame["linked_to_response"])
        result = backend.get_session_results(self.session_id)["results"][0]
        self.assertEqual(result["face_image_files"], [frame["image_file"]])

    def test_end_early_is_idempotent_and_blocks_new_work(self):
        """Ending twice preserves the end time and rejects new scenarios."""
        self.start(1)
        self.recovery()
        first = backend.end_session(
            backend.SessionEnd(session_id=self.session_id)
        )
        again = backend.end_session(
            backend.SessionEnd(session_id=self.session_id)
        )
        self.assertEqual(first["session_status"], "ended_early")
        self.assertFalse(first["already_ended"])
        self.assertTrue(again["already_ended"])
        self.assertEqual(first["ended_at"], again["ended_at"])
        with self.assertRaises(HTTPException) as ctx:
            self.start(2)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_all_scenarios_skipped_are_reported_separately(self):
        """Skipped scenarios are not counted as answered questions."""
        for scenario in (1, 2, 3, 4):
            self.start(scenario)
            self.recovery(scenario_id=scenario)
        ended = backend.end_session(
            backend.SessionEnd(session_id=self.session_id)
        )
        self.assertEqual(ended["session_status"], "completed_with_skips")
        self.assertEqual(ended["completed_scenarios"], 0)
        self.assertEqual(ended["skipped_scenarios"], 4)


    def test_real_facial_result_is_saved_and_used_by_report(self):
        """Real CV output is recorded once and included in the report."""
        self.start(1)
        frame = asyncio.run(backend.upload_session_frame(
            session_id=self.session_id, scenario_id=1, frame=sample_image()
        ))
        self.submit(1)
        with mock.patch.object(
            backend, "classify_facial_frame",
            return_value={"dominant_emotion": "Happy", "confidence": 0.91}
        ) as inference:
            first = backend.evaluate_facial_frame(self.event(1))
            again = backend.evaluate_facial_frame(self.event(1))
        self.assertEqual(inference.call_count, 1)
        self.assertFalse(first["already_evaluated"])
        self.assertTrue(again["already_evaluated"])
        self.assertEqual(first["facial_result"]["source"], "resmaskingnet")
        self.assertEqual(first["facial_result"]["image_file"], frame["image_file"])
        self.assertEqual(
            len(backend.sessions[self.session_id]["results"][0]["facial_observations"]), 1
        )
        report = backend.generate_session_report(self.session_id)
        self.assertEqual(report["facial_analysis"]["model_observations"], 1)
        self.assertEqual(report["facial_analysis"]["most_frequent_expression"], "Happy")
        self.assertEqual(
            report["scenario_details"][0]["verbal_facial_comparison"], "Agreement"
        )

    def test_facial_evaluation_requires_a_saved_response_and_frame(self):
        """Facial analysis needs both a saved answer and camera frame."""
        self.start(1)
        with self.assertRaises(HTTPException) as missing_answer:
            backend.evaluate_facial_frame(self.event(1))
        self.assertEqual(missing_answer.exception.status_code, 409)

        self.submit(1)
        with self.assertRaises(HTTPException) as missing_frame:
            backend.evaluate_facial_frame(self.event(1))
        self.assertEqual(missing_frame.exception.status_code, 404)

    def test_no_face_does_not_create_a_real_observation(self):
        """A frame with no detected face must not create model statistics."""
        self.start(1)
        asyncio.run(backend.upload_session_frame(
            session_id=self.session_id, scenario_id=1, frame=sample_image()
        ))
        self.submit(1)
        with mock.patch.object(
            backend, "classify_facial_frame", return_value=None
        ):
            with self.assertRaises(HTTPException) as error:
                backend.evaluate_facial_frame(self.event(1))
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(
            backend.generate_session_report(self.session_id)["facial_analysis"][
                "model_observations"
            ], 0
        )

    def test_mock_observation_is_excluded_from_real_report(self):
        """Manual/mock face results remain separate from real CV metrics."""
        self.start(1)
        self.submit(1)
        observation = backend.save_facial_result(
            backend.FacialResult(
                session_id=self.session_id,
                scenario_id=1,
                dominant_emotion="Happy",
                confidence=0.90
            )
        )
        self.assertEqual(observation["facial_result"]["source"], "mock")
        report = backend.generate_session_report(self.session_id)
        self.assertEqual(report["facial_analysis"]["model_observations"], 0)
        self.assertEqual(report["facial_analysis"]["mock_observations_excluded"], 1)
        self.assertEqual(
            report["scenario_details"][0]["verbal_facial_comparison"], "Unavailable"
        )


class FacialClassifierTests(unittest.TestCase):
    """Unit tests for RMN normalization and router registration."""
    def test_normalizes_rmn_output_and_rejects_missing_or_multiple_faces(self):
        """Normalize valid RMN output, and reject ambiguous/invalid detections."""
        from backend.facial_classifier import (
            FacialInferenceError, normalize_detections
        )
        self.assertEqual(
            normalize_detections([{"emo_label": "happy", "emo_proba": 0.87}]),
            {"dominant_emotion": "Happy", "confidence": 0.87}
        )
        self.assertIsNone(normalize_detections([]))
        with self.assertRaises(FacialInferenceError):
            normalize_detections([
                {"emo_label": "happy", "emo_proba": 0.9},
                {"emo_label": "sad", "emo_proba": 0.8}
            ])
        with self.assertRaises(FacialInferenceError):
            normalize_detections([{"emo_label": "happy", "emo_proba": 1.5}])

    def test_audio_and_vision_routes_keep_original_api_paths(self):
        """Protect legacy endpoints and callable aliases after modularization."""
        route_counts = {}
        for route in backend.app.routes:
            for method in getattr(route, "methods", []):
                route_counts[(method, route.path)] = (
                    route_counts.get((method, route.path), 0) + 1
                )

        expected = [
            ("POST", "/api/audio/upload"),
            ("POST", "/api/audio/capture"),
            ("POST", "/api/audio/evaluate"),
            ("POST", "/api/camera/frame"),
            ("POST", "/api/camera/raw-frame"),
            ("POST", "/api/camera/session-frame"),
            ("POST", "/api/facial/evaluate"),
            ("POST", "/api/facial/result"),
            ("POST", "/api/session/start"),
            ("POST", "/api/session/end"),
            ("GET", "/api/scenario/next"),
            ("POST", "/api/scenario/start"),
            ("POST", "/api/scenario/complete"),
            ("POST", "/api/scenario/recovery"),
            ("POST", "/api/response/submit"),
            ("GET", "/api/session/{session_id}"),
            ("GET", "/api/session/{session_id}/report"),
            ("GET", "/api/session/{session_id}/report/view"),
        ]
        for method, path in expected:
            self.assertEqual(route_counts.get((method, path)), 1, path)

        from backend import audio, vision
        self.assertIs(backend.evaluate_audio, audio.evaluate_audio)
        self.assertIs(backend.upload_session_frame, vision.upload_session_frame)
        self.assertIs(backend.evaluate_facial_frame, vision.evaluate_facial_frame)


class TransferTests(unittest.TestCase):
    """Unit tests for the session-aware transfer CLI."""
    def test_default_robot_audio_matches_choregraphe(self):
        """Keep the transfer script's audio path aligned with Choregraphe."""
        self.assertEqual(nao_transfer.DEFAULT_NAO_AUDIO,
                         "/home/nao/response.wav")

    @mock.patch.object(nao_transfer.requests, "post")
    @mock.patch.object(nao_transfer.requests, "get")
    def test_file_uploads_use_matching_session_and_scenario(
        self, mock_get, mock_post
    ):
        """Audio and images must be uploaded with consistent scenario IDs."""
        with tempfile.TemporaryDirectory() as folder:
            wav = Path(folder) / "response.wav"
            jpg = Path(folder) / "face.jpg"
            wav.write_bytes(b"RIFFdemo")
            jpg.write_bytes(b"image-demo")
            mock_get.return_value.json.return_value = {
                "session_status": "active", "active_scenario_id": 2
            }
            mock_post.return_value.json.return_value = {"status": "success"}
            result = nao_transfer.upload_captures(
                "example-session", 2,
                audio_path=wav, image_paths=[jpg]
            )
        self.assertEqual(mock_post.call_count, 2)
        endpoints = [call.args[0] for call in mock_post.call_args_list]
        self.assertTrue(endpoints[0].endswith("/api/camera/session-frame"))
        self.assertTrue(endpoints[1].endswith("/api/audio/evaluate"))
        for call in mock_post.call_args_list:
            self.assertEqual(call.kwargs["data"], {
                "session_id": "example-session", "scenario_id": "2"
            })
        self.assertIsNotNone(result["audio"])

    @mock.patch.object(nao_transfer.requests, "post")
    @mock.patch.object(nao_transfer.requests, "get")
    def test_mismatched_scenario_is_rejected(self, mock_get, mock_post):
        """Do not transfer files to a different active scenario."""
        mock_get.return_value.json.return_value = {
            "session_status": "active", "active_scenario_id": 3
        }
        with self.assertRaises(RuntimeError):
            nao_transfer.upload_captures(
                "test-session", 1, audio_path="missing.wav"
            )
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

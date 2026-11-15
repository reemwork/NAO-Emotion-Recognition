"""Offline checks for the one-session MVP runner (no NAO or Ollama needed)."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_FILE = Path(__file__).resolve().parents[1] / "scripts" / "run_mvp_session.py"
spec = importlib.util.spec_from_file_location("mvp_runner", MODULE_FILE)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class FakeResponse:
    def __init__(self, data=None, text=""):
        self.data = data or {}
        self.text = text

    def json(self):
        return self.data


class TestMVPController(unittest.TestCase):
    def test_four_scenarios_run_sequentially_and_save_reports(self):
        events = []

        def fake_api(method, api_url, endpoint, **kwargs):
            events.append((method, endpoint))
            if endpoint == "/api/scenario/next":
                return FakeResponse({"has_more": True,
                                     "scenario": {"scenario_id": kwargs["params"]["index"] + 1}})
            if endpoint == "/api/session/start":
                return FakeResponse({"session_id": "one-session"})
            if endpoint == "/api/response/submit":
                return FakeResponse({"saved_result": {"evaluation": "Correct"}})
            if endpoint == "/api/session/end":
                return FakeResponse({"session_status": "completed"})
            if endpoint == "/api/session/one-session":
                return FakeResponse({"total_responses": 4, "skipped_scenarios": 0})
            if endpoint.endswith("/report/view"):
                return FakeResponse(text="<html>test</html>")
            if endpoint.endswith("/report"):
                return FakeResponse({"report_type": "Technical Prototype Report"})
            return FakeResponse({"status": "success"})

        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "request_api", fake_api):
            sid = runner.run_session("http://example", runner.load_cases(), Path(tmp))
            out = Path(tmp) / sid
            self.assertEqual(sid, "one-session")
            self.assertEqual(json.loads((out / "session_report.json").read_text())[
                "report_type"], "Technical Prototype Report")
            self.assertEqual((out / "session_report.html").read_text(), "<html>test</html>")
            self.assertEqual(sum(e[1] == "/api/scenario/complete" for e in events), 4)
            self.assertEqual(sum(e[1] == "/api/response/submit" for e in events), 4)
            self.assertEqual(sum(e[1] == "/api/scenario/start" for e in events), 4)
            self.assertEqual(events[-1][1], "/api/session/one-session/report/view")

    def test_no_response_skips_without_submitting_answer(self):
        requests_seen = []

        def fake_api(method, api_url, endpoint, **kwargs):
            requests_seen.append((endpoint, kwargs))
            if endpoint == "/api/scenario/next":
                return FakeResponse({"has_more": True, "scenario": {"scenario_id": 1}})
            if endpoint == "/api/session/start":
                return FakeResponse({"session_id": "skip-session"})
            if endpoint == "/api/session/end":
                return FakeResponse({"session_status": "completed_with_skips"})
            if endpoint == "/api/session/skip-session":
                return FakeResponse({"total_responses": 0, "skipped_scenarios": 1})
            if endpoint.endswith("/report/view"):
                return FakeResponse(text="<html></html>")
            return FakeResponse({})

        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "request_api", fake_api):
            runner.run_session(
                "http://example", [{"scenario_id": 1, "no_response": True}], tmp
            )
        endpoint_names = [entry[0] for entry in requests_seen]
        self.assertIn("/api/scenario/recovery", endpoint_names)
        self.assertNotIn("/api/response/submit", endpoint_names)
        self.assertNotIn("/api/scenario/complete", endpoint_names)
        recovery = next(kwargs["json"] for ep, kwargs in requests_seen
                        if ep == "/api/scenario/recovery")
        self.assertEqual(recovery["reason"], "no_response")

    def test_invalid_cases_are_rejected_before_start(self):
        with self.assertRaises(ValueError):
            runner.load_cases(limit=0)
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "input.json"
            config.write_text('[{"scenario_id":1,"text":"Hello","no_response":true}]')
            with self.assertRaises(ValueError):
                runner.load_cases(config)


if __name__ == "__main__":
    unittest.main()

"""Run one NAO prototype session from a laptop using the existing FastAPI API."""

import argparse
import json
import sys
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API = "http://127.0.0.1:8000"
DEMO_CASES = [
    {"scenario_id": 1, "text": "She is smiling because she is happy."},
    {"scenario_id": 2, "text": "He is crying and looks sad."},
    {"scenario_id": 3, "text": "She looks angry and frustrated."},
    {"scenario_id": 4, "text": "The person has a calm, neutral expression."},
]


def request_api(method, api_url, endpoint, **kwargs):
    """Send an HTTP request and show useful errors if the API rejects it."""
    timeout = kwargs.pop("timeout", 30)
    try:
        response = requests.request(
            method, f"{api_url.rstrip('/')}{endpoint}", timeout=timeout, **kwargs
        )
        response.raise_for_status()
        return response
    except requests.RequestException as error:
        detail = ""
        if error.response is not None:
            detail = f" | {error.response.status_code}: {error.response.text[:300]}"
        raise RuntimeError(f"{method} {endpoint} failed{detail}: {error}") from error


def load_cases(input_path=None, limit=None):
    if input_path:
        with Path(input_path).open(encoding="utf-8") as file:
            cases = json.load(file)
        if isinstance(cases, dict):
            cases = cases.get("scenarios")
    else:
        cases = [item.copy() for item in DEMO_CASES]

    if not isinstance(cases, list) or not cases:
        raise ValueError("Input must contain a non-empty list of scenarios.")
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be at least 1.")
        cases = cases[:limit]

    seen = set()
    for item in cases:
        if not isinstance(item, dict) or type(item.get("scenario_id")) is not int:
            raise ValueError("Every scenario needs a numeric scenario_id.")
        scenario_id = item["scenario_id"]
        if scenario_id in seen:
            raise ValueError(f"Duplicate scenario ID: {scenario_id}")
        seen.add(scenario_id)

        choices = sum((
            bool(item.get("text")), bool(item.get("audio")),
            item.get("no_response") is True
        ))
        if choices != 1:
            raise ValueError(
                f"Scenario {scenario_id}: set exactly one of text, audio, or no_response."
            )
        for key in ("audio", "face_image"):
            if item.get(key):
                file_path = PROJECT_ROOT / item[key]
                if not file_path.is_file():
                    raise FileNotFoundError(f"Scenario {scenario_id}: missing {key}: {file_path}")
                if key == "audio" and file_path.suffix.lower() != ".wav":
                    raise ValueError(f"Scenario {scenario_id}: audio must be .wav")
                if key == "face_image" and file_path.suffix.lower() not in {
                    ".jpg", ".jpeg", ".png"
                }:
                    raise ValueError(f"Scenario {scenario_id}: face_image must be JPG or PNG")
    return cases


def upload_image(api_url, session_id, scenario_id, file_path):
    with file_path.open("rb") as image:
        request_api(
            "POST", api_url, "/api/camera/session-frame",
            data={"session_id": session_id, "scenario_id": scenario_id},
            files={"frame": (file_path.name, image)},
            timeout=60,
        )


def evaluate_answer(api_url, session_id, item):
    payload = {"session_id": session_id, "scenario_id": item["scenario_id"]}
    if item.get("no_response") is True:
        request_api(
            "POST", api_url, "/api/scenario/recovery",
            json={**payload, "action": "skip", "reason": "no_response"},
        )
        return "No Response"

    if item.get("audio"):
        audio_path = PROJECT_ROOT / item["audio"]
        with audio_path.open("rb") as audio:
            result = request_api(
                "POST", api_url, "/api/audio/evaluate",
                data=payload,
                files={"audio": (audio_path.name, audio, "audio/wav")},
                timeout=360,
            ).json()
    else:
        result = request_api(
            "POST", api_url, "/api/response/submit",
            json={**payload, "spoken_text": item["text"]},
            timeout=240,
        ).json()
    return result["saved_result"]["evaluation"]


def run_session(api_url, cases, output_root):
    # Verify scenario order before creating a session.
    for index, item in enumerate(cases):
        response = request_api(
            "GET", api_url, "/api/scenario/next", params={"index": index}
        ).json()
        actual = response.get("scenario", {}).get("scenario_id")
        if not response.get("has_more") or actual != item["scenario_id"]:
            raise ValueError(
                f"Scenario order mismatch at position {index + 1}: "
                f"backend={actual}, input={item['scenario_id']}"
            )

    session_id = request_api("POST", api_url, "/api/session/start").json()["session_id"]
    print(f"Session started: {session_id}", flush=True)
    warnings = []

    try:
        for item in cases:
            scenario_id = item["scenario_id"]
            payload = {"session_id": session_id, "scenario_id": scenario_id}
            print(f"\nScenario {scenario_id}: starting", flush=True)
            request_api("POST", api_url, "/api/scenario/start", json=payload)

            if item.get("face_image"):
                upload_image(
                    api_url, session_id, scenario_id,
                    PROJECT_ROOT / item["face_image"]
                )

            evaluation = evaluate_answer(api_url, session_id, item)
            print(f"Scenario {scenario_id}: {evaluation}", flush=True)
            if evaluation == "No Response":
                continue

            if item.get("face_image"):
                try:
                    facial = request_api(
                        "POST", api_url, "/api/facial/evaluate",
                        json=payload, timeout=240,
                    ).json()
                    label = facial["facial_result"]["dominant_emotion"]
                    print(f"Scenario {scenario_id}: facial expression = {label}")
                except RuntimeError as error:
                    # Facial inference is independent of verbal correctness.
                    warnings.append(f"Scenario {scenario_id}: {error}")
                    print(f"WARNING: facial analysis unavailable for scenario {scenario_id}")

            request_api("POST", api_url, "/api/scenario/complete", json=payload)

        end = request_api(
            "POST", api_url, "/api/session/end", json={"session_id": session_id}
        ).json()
        summary = request_api("GET", api_url, f"/api/session/{session_id}").json()
        report = request_api(
            "GET", api_url, f"/api/session/{session_id}/report"
        ).json()
        report_html = request_api(
            "GET", api_url, f"/api/session/{session_id}/report/view"
        ).text

        output_dir = Path(output_root) / session_id
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "session_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (output_dir / "session_report.html").write_text(
            report_html, encoding="utf-8"
        )
        (output_dir / "session_progress.json").write_text(
            json.dumps({"session": summary, "warnings": warnings}, indent=2,
                       ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nSession ended: {end['session_status']}")
        print(f"Responses: {summary['total_responses']}")
        print(f"Skipped: {summary['skipped_scenarios']}")
        print(f"Report: {output_dir / 'session_report.html'}")
        if warnings:
            print(f"Facial analysis warnings: {len(warnings)} (see session_progress.json)")
        return session_id

    except Exception:
        print(
            f"\nSession {session_id} stopped before completion. "
            "It remains saved in the backend for inspection.",
            file=sys.stderr,
        )
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Run one sequential prototype session through the FastAPI backend."
    )
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--input", type=Path, help="JSON scenarios with text or WAV files")
    parser.add_argument("--limit", type=int, help="Run only the first N scenarios")
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "data" / "mvp_runs"
    )
    args = parser.parse_args()
    try:
        cases = load_cases(args.input, args.limit)
        run_session(args.api_url, cases, args.output_dir)
    except (RuntimeError, ValueError, FileNotFoundError, KeyError,
            requests.RequestException) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()

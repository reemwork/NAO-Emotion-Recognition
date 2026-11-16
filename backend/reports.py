# NAO_SESSION_REPORT_INTEGRATION_V1
"""Independent verbal-performance and facial-observation session reports.

Facial expressions are descriptive observations for specialist review.
They are never compared against verbal predictions or used to judge engagement.
"""

from collections import Counter, defaultdict
from html import escape
from math import isfinite
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

import backend

router = APIRouter(tags=["Session Reports"])


def _backend():
    """Use the same loaded application state as the other API routes."""
    return backend.app


def _session(session_id):
    session = _backend().sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


def _scenario_frames(session, results):
    """Collect captured image paths, including frames awaiting analysis."""
    by_scenario = defaultdict(list)

    def add(scenario_id, path):
        if not path:
            return
        try:
            scenario_id = int(scenario_id)
        except (ValueError, TypeError):
            return
        path = str(path)
        if path not in by_scenario[scenario_id]:
            by_scenario[scenario_id].append(path)

    for scenario_id, paths in (session.get("captured_frames") or {}).items():
        for path in (paths or []):
            add(scenario_id, path)

    for result in results:
        scenario_id = result.get("scenario_id")
        for path in (result.get("face_image_files") or []):
            add(scenario_id, path)
        add(scenario_id, result.get("face_image_file"))
        for observation in (result.get("facial_observations") or []):
            if observation.get("source") == "resmaskingnet":
                add(scenario_id, observation.get("image_file"))

    return by_scenario


def _confidence_percent(confidence):
    """Convert a model probability to a percentage, or return None."""
    try:
        value = float(confidence)
        return round(100 * value, 2) if isfinite(value) and 0 <= value <= 1 else None
    except (TypeError, ValueError):
        return None


@router.get("/api/session/{session_id}/report")
def generate_session_report(session_id: str):
    """Return independent verbal results and camera observations."""
    ctx = _backend()
    session = _session(session_id)
    results = session.get("results") or []

    correct = sum(r.get("evaluation") == "Correct" for r in results)
    incorrect = sum(r.get("evaluation") == "Incorrect" for r in results)
    unclear = sum(r.get("evaluation") == "Unclear" for r in results)
    evaluated = correct + incorrect
    accuracy = round(100 * correct / evaluated, 2) if evaluated else None

    # A submitted response is not necessarily a *completed* scenario.
    progress = session.get("scenario_progress") or {}
    completed = sum(
        1 for item in progress.values()
        if isinstance(item, dict) and item.get("status") == "completed"
    )

    verbal_details = [{
        "scenario_id": r.get("scenario_id"),
        "reference_label": r.get("reference_label"),
        "spoken_text": r.get("spoken_text"),
        "verbal_emotion": r.get("predicted_emotion"),
        "answer_evaluation": r.get("evaluation"),
    } for r in results]

    emotions = []
    mock_count = 0
    observations = []
    by_image = defaultdict(list)

    def add_observation(scenario_id, observation):
        nonlocal mock_count
        source = observation.get("source")
        if source == "mock":
            mock_count += 1
            return
        if source != "resmaskingnet":
            return
        emotion = observation.get("dominant_emotion")
        if emotion:
            emotions.append(str(emotion))
        record = {
            "scenario_id": scenario_id,
            "observation_id": observation.get("observation_id"),
            "image_file": observation.get("image_file"),
            "dominant_expression": emotion,
            "confidence": observation.get("confidence"),
            "confidence_percent": _confidence_percent(observation.get("confidence")),
            "recorded_at": observation.get("recorded_at"),
            "source": "resmaskingnet",
        }
        observations.append(record)
        if record["image_file"]:
            by_image[(str(scenario_id), str(record["image_file"]))].append(record)

    # Legacy/manual evaluations, previously stored alongside verbal responses.
    for result in results:
        for observation in (result.get("facial_observations") or []):
            add_observation(result.get("scenario_id"), observation)

    # Live NAO observations: independent of whether a verbal answer exists.
    for scenario_id, records in (session.get("facial_observations") or {}).items():
        for observation in (records or []):
            add_observation(scenario_id, observation)

    # Compare verbal and facial emotions for reporting only.
    # Mock observations must never influence the comparison.
    # Facial expressions do not determine verbal correctness.
    for detail in verbal_details:
        scenario_id = str(detail["scenario_id"])
        verbal_emotion = detail["verbal_emotion"]

        real_emotions = [
            obs["dominant_expression"]
            for obs in observations
            if str(obs["scenario_id"]) == scenario_id
            and obs["dominant_expression"] is not None
        ]

        if real_emotions:
            dominant_facial = Counter(real_emotions).most_common(1)[0][0]
        else:
            dominant_facial = None

        if (
            dominant_facial is None
            or verbal_emotion is None
            or verbal_emotion == "Unclear"
        ):
            comparison = "Unavailable"

        elif verbal_emotion == dominant_facial:
            comparison = "Agreement"

        else:
            comparison = "Mismatch"

        detail["dominant_facial_expression"] = dominant_facial
        detail["verbal_facial_comparison"] = comparison

    frames = []
    for scenario_id, paths in sorted(_scenario_frames(session, results).items()):
        for index, path in enumerate(paths):
            # If the same frame was evaluated more than once, show the latest result.
            matching = by_image.get((str(scenario_id), path), [])
            last = matching[-1] if matching else None
            frames.append({
                "scenario_id": scenario_id,
                "frame_index": index,
                "image_file": path,
                "image_url": (
                    f"/api/session/{quote(session_id, safe='')}/report/frame/"
                    f"{scenario_id}/{index}"
                ),
                "analysis_status": "Analyzed" if last else (session.get("camera_analysis_status") or {}).get(path, "Not analyzed"),
                "capture_source": (session.get("camera_capture_sources") or {}).get(
                    path, "Source not verified"
                ),
                "dominant_expression": last["dominant_expression"] if last else None,
                "confidence_percent": last["confidence_percent"] if last else None,
                "recorded_at": last["recorded_at"] if last else None,
            })

    most_frequent = Counter(emotions).most_common(1)[0][0] if emotions else None

    return {
        "session_id": session_id,
        "report_type": "Technical Prototype Report",
        "session_status": session.get("status") or session.get("session_status") or "Unknown",
        "session_started_at": session.get("started_at"),
        "session_ended_at": session.get("ended_at"),
        "total_scenarios": len(ctx.scenarios_db),
        "completed_scenarios": completed,
        "answered_scenarios": len(results),
        "verbal_performance": {
            "correct": correct,
            "incorrect": incorrect,
            "unclear": unclear,
            "accuracy_excluding_unclear": accuracy,
        },
        "scenario_details": verbal_details,
        "facial_analysis": {
            "captured_frames": len(frames),
            "model_observations": len(observations),
            "mock_observations_excluded": mock_count,
            "most_frequent_expression": most_frequent,
            "observations": observations,
            "frames": frames,
        },
    }


@router.get("/api/session/{session_id}/report/frame/{scenario_id}/{frame_index}")
def view_session_frame(session_id: str, scenario_id: int, frame_index: int):
    """Serve a frame belonging to this session, never an arbitrary disk path."""
    session = _session(session_id)
    frames_by_scenario = _scenario_frames(session, session.get("results") or [])
    paths = frames_by_scenario.get(scenario_id, [])
    if not 0 <= frame_index < len(paths):
        raise HTTPException(status_code=404, detail="Frame not found.")

    root = Path(_backend().ROOT).resolve()
    allowed_root = (root / "data" / "session_frames").resolve()
    allowed_session_dir = (allowed_root / session_id).resolve()
    relative_path = Path(paths[frame_index])

    # Never expose files outside this session's captured-frame directory.
    if (
        relative_path.is_absolute()
        or not allowed_session_dir.is_relative_to(allowed_root)
    ):
        raise HTTPException(status_code=404, detail="Frame not found.")

    full_path = (root / relative_path).resolve()
    if not full_path.is_relative_to(allowed_session_dir) or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Frame not found.")

    return FileResponse(full_path, headers={"Cache-Control": "no-store"})


@router.get("/api/session/{session_id}/report/view", response_class=HTMLResponse)
def view_session_report(session_id: str):
    """Render a print-friendly report with separate verbal and face sections."""
    # Preserve the application-level alias used by existing offline tests.
    report_function = getattr(_backend(), "generate_session_report", generate_session_report)
    report = report_function(session_id)
    performance = report["verbal_performance"]
    facial = report["facial_analysis"]

    def safe(value):
        return escape(str(value if value is not None else "N/A"), quote=True)

    accuracy = performance["accuracy_excluding_unclear"]
    accuracy_text = f"{accuracy}%" if accuracy is not None else "N/A"

    verbal_rows = "".join(f"""
      <tr>
        <td>{safe(item['scenario_id'])}</td>
        <td>{safe(item['reference_label'])}</td>
        <td>{safe(item['spoken_text'])}</td>
        <td>{safe(item['verbal_emotion'])}</td>
        <td>{safe(item['answer_evaluation'])}</td>
      </tr>""" for item in report["scenario_details"])
    if not verbal_rows:
        verbal_rows = '<tr><td colspan="5">No verbal responses recorded.</td></tr>'

    frame_cards = ""
    for frame in facial["frames"]:
        expression = safe(frame["dominant_expression"])
        confidence = frame["confidence_percent"]
        confidence_text = f"{confidence:.2f}%" if confidence is not None else "N/A"
        label = (
            f"{expression} · {confidence_text}"
            if frame["analysis_status"] == "Analyzed"
            else safe(frame["analysis_status"])
        )
        frame_cards += f"""
        <article class="frame-card">
          <img src="{safe(frame['image_url'])}"
               alt="Captured camera frame from scenario {safe(frame['scenario_id'])}"
               loading="lazy">
          <div class="frame-body">
            <strong>Scenario {safe(frame['scenario_id'])} · Frame {safe(frame['frame_index'] + 1)}</strong>
            <div class="muted">Capture source: {safe(frame['capture_source'])}</div>
            <div class="muted">Model observation: {label}</div>
            <div class="muted">Analysis time: {safe(frame['recorded_at'])}</div>
          </div>
        </article>"""
    if not frame_cards:
        frame_cards = '<p class="muted">No camera frames captured for this session.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NAO Session Report</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: Arial, sans-serif; color: #243447; max-width: 1100px;
            margin: 30px auto; padding: 0 20px; line-height: 1.5; }}
    h1, h2 {{ color: #174a75; }}
    h1 {{ margin-bottom: 4px; }}
    h2 {{ font-size: 20px; margin: 0 0 12px; }}
    .muted {{ color: #60758b; font-size: 13px; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 12px 30px; margin: 16px 0 25px; }}
    .section {{ background: #f1f6fa; padding: 20px; border-radius: 10px; margin: 20px 0; }}
    .metrics {{ display: flex; gap: 14px; flex-wrap: wrap; }}
    .metric {{ background: white; padding: 12px 16px; border-radius: 8px; min-width: 130px; }}
    .metric strong {{ display: block; color: #174a75; font-size: 22px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; background: white; }}
    th, td {{ border: 1px solid #cad6df; padding: 10px; text-align: left;
              overflow-wrap: anywhere; }}
    th {{ background: #e5eef5; }}
    .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
               gap: 16px; margin-top: 16px; }}
    .frame-card {{ background: white; border: 1px solid #cad6df;
                  border-radius: 8px; overflow: hidden; }}
    .frame-card img {{ display: block; width: 100%; height: 210px;
                       object-fit: contain; background: #e4eaf0; }}
    .frame-body {{ padding: 12px; }}
    .note {{ font-size: 12px; color: #60758b; margin: 22px 0; }}
    @media print {{
      body {{ margin: 0; max-width: none; padding: 8mm; }}
      .section, .frame-card, tr {{ break-inside: avoid; }}
      .gallery {{ grid-template-columns: repeat(3, 1fr); }}
    }}
  </style>
</head>
<body>
  <h1>NAO Emotion Recognition</h1>
  <p class="muted">Technical Prototype Session Report</p>
  <div class="meta">
    <span><strong>Session:</strong> {safe(report['session_id'])}</span>
    <span><strong>Status:</strong> {safe(report['session_status'])}</span>
    <span><strong>Completed:</strong> {safe(report['completed_scenarios'])} / {safe(report['total_scenarios'])}</span>
    <span><strong>Responses:</strong> {safe(report['answered_scenarios'])}</span>
  </div>

  <section class="section">
    <h2>1. Verbal Response Evaluation</h2>
    <div class="metrics">
      <div class="metric"><span class="muted">Correct</span><strong>{performance['correct']}</strong></div>
      <div class="metric"><span class="muted">Incorrect</span><strong>{performance['incorrect']}</strong></div>
      <div class="metric"><span class="muted">Unclear</span><strong>{performance['unclear']}</strong></div>
      <div class="metric"><span class="muted">Accuracy (excluding unclear)</span><strong>{accuracy_text}</strong></div>
    </div>
    <h3>Verbal Responses by Scenario</h3>
    <table>
      <thead><tr><th>ID</th><th>Reference Label</th><th>Spoken Response</th>
          <th>Predicted Emotion</th><th>Answer Evaluation</th></tr></thead>
      <tbody>{verbal_rows}</tbody>
    </table>
  </section>

  <section class="section">
    <h2>2. Facial Expression Observations — For Specialist Review</h2>
    <p class="muted">Camera captures and model outputs are provided as descriptive evidence.
       Facial expressions do not affect verbal correctness and are not an automated engagement score.</p>
    <div class="metrics">
      <div class="metric"><span class="muted">Captured Frames</span><strong>{facial['captured_frames']}</strong></div>
      <div class="metric"><span class="muted">Model Observations</span><strong>{facial['model_observations']}</strong></div>
      <div class="metric"><span class="muted">Most Frequent Expression</span><strong>{safe(facial['most_frequent_expression'])}</strong></div>
    </div>
    <p class="muted">Mock observations excluded: {facial['mock_observations_excluded']}</p>
    <h3>Captured Camera Frames</h3>
    <div class="gallery">{frame_cards}</div>
  </section>

  <p class="note">Prototype report based on predefined test scenarios. Facial expression
     observations require human interpretation and are not a clinical or engagement assessment.
     This report contains potentially sensitive face images; handle and share it securely.</p>
</body>
</html>"""

"""JSON/HTML session reporting.

A report includes verbal answer correctness and an independent, descriptive
summary of facial observations; it makes no clinical assessment.
"""
from collections import Counter
from html import escape
import backend
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Session Reports"])

def _backend():
    """Look up the same sessions and report implementation used by the API."""
    # Use the already loaded package module (no recursive re-import).
    # This also preserves monkeypatched backend.app aliases in offline tests.
    return backend.app

@router.get("/api/session/{session_id}/report")
def generate_session_report(session_id: str):
    """Summarize verbal correctness and observed facial expressions by scenario.
    
        Mock facial readings are excluded from real model counts. Matching
        verbal/facial labels is descriptive; it does NOT decide correctness."""

    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db

    session = sessions.get(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    results = session["results"]

    correct = sum(
        r.get("evaluation") == "Correct"
        for r in results
    )

    incorrect = sum(
        r.get("evaluation") == "Incorrect"
        for r in results
    )

    unclear = sum(
        r.get("evaluation") == "Unclear"
        for r in results
    )

    # Accuracy excludes Unclear answers: its denominator is correct + incorrect.
    evaluated = correct + incorrect

    accuracy = (
        round(correct / evaluated * 100, 2)
        if evaluated > 0 else None
    )

    facial_emotions = []
    mock_count = 0
    scenario_reports = []

    for result in results:

        observations = result.get(
            "facial_observations", []
        )

        # A manually submitted mock observation must never inflate model metrics.
        real_observations = []

        for obs in observations:
            if obs.get("source") == "mock":
                mock_count += 1

            elif obs.get("source") == "resmaskingnet":
                real_observations.append(obs)
                facial_emotions.append(
                    obs["dominant_emotion"]
                )

        verbal_emotion = result.get(
            "predicted_emotion"
        )

        if real_observations:

            dominant_facial = Counter(
                obs["dominant_emotion"]
                for obs in real_observations
            ).most_common(1)[0][0]

            # Agreement is descriptive and not a score of actual feelings.
            if verbal_emotion == "Unclear":
                comparison = "Unavailable"

            elif verbal_emotion == dominant_facial:
                comparison = "Agreement"

            else:
                comparison = "Mismatch"

        else:
            dominant_facial = None
            comparison = "Unavailable"

        scenario_reports.append({
            "scenario_id": result["scenario_id"],
            "reference_label": result["reference_label"],
            "spoken_text": result["spoken_text"],
            "verbal_emotion": verbal_emotion,
            "answer_evaluation": result["evaluation"],
            "dominant_facial_expression": dominant_facial,
            "verbal_facial_comparison": comparison
        })

    most_frequent_facial = (
        Counter(facial_emotions).most_common(1)[0][0]
        if facial_emotions else None
    )

    return {
        "session_id": session_id,
        "report_type": "Technical Prototype Report",
        "total_scenarios": len(scenarios_db),
        "completed_scenarios": len(results),
        "verbal_performance": {
            "correct": correct,
            "incorrect": incorrect,
            "unclear": unclear,
            "accuracy_excluding_unclear": accuracy
        },
        "facial_analysis": {
            "model_observations": len(facial_emotions),
            "mock_observations_excluded": mock_count,
            "most_frequent_expression": most_frequent_facial
        },
        "scenario_details": scenario_reports
    }

@router.get(
    "/api/session/{session_id}/report/view",
    response_class=HTMLResponse
)
def view_session_report(session_id: str):
    """Render the JSON session report as escaped, print-friendly HTML."""

    generate_session_report = _backend().generate_session_report

    report = generate_session_report(session_id)

    performance = report["verbal_performance"]
    facial = report["facial_analysis"]

    accuracy = performance["accuracy_excluding_unclear"]
    accuracy_text = (
        f"{accuracy}%"
        if accuracy is not None
        else "N/A"
    )

    # Escape all text inserted into HTML, including untrusted spoken responses.
    rows = ""

    for item in report["scenario_details"]:
        rows += f"""
        <tr>
            <td>{item['scenario_id']}</td>
            <td>{escape(str(item['reference_label']))}</td>
            <td>{escape(str(item['spoken_text']))}</td>
            <td>{escape(str(item['verbal_emotion']))}</td>
            <td>{escape(str(item['answer_evaluation']))}</td>
            <td>{escape(str(item['dominant_facial_expression'] or 'N/A'))}</td>
            <td>{escape(str(item['verbal_facial_comparison']))}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="7">No completed scenarios.</td></tr>'

    styles = """
    <style>
        body {
            font-family: Arial, sans-serif;
            color: #203047;
            margin: 40px;
            line-height: 1.6;
        }
        h1, h2 { color: #174a75; }
        .subtitle { color: #66788a; }
        .section {
            background: #f1f6fa;
            padding: 18px;
            border-radius: 8px;
            margin: 20px 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        th, td {
            border: 1px solid #cad6df;
            padding: 8px;
            text-align: left;
            overflow-wrap: anywhere;
        }
        th { background: #e5eef5; }
        .note { font-size: 12px; color: #66788a; }
        @media print {
            body { margin: 15mm; }
            .section { break-inside: avoid; }
        }
    </style>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>NAO Session Report</title>
        {styles}
    </head>
    <body>
        <h1>NAO Emotion Recognition</h1>
        <p class="subtitle">Technical Prototype Session Report</p>

        <p><strong>Session ID:</strong> {escape(session_id)}</p>
        <p><strong>Completed Scenarios:</strong>
        {report['completed_scenarios']} /
        {report['total_scenarios']}</p>

        <div class="section">
            <h2>Verbal Performance</h2>
            <p>Correct: {performance['correct']}</p>
            <p>Incorrect: {performance['incorrect']}</p>
            <p>Unclear: {performance['unclear']}</p>
            <p>Accuracy (excluding unclear):
            {accuracy_text}</p>
        </div>

        <div class="section">
            <h2>Facial Expression Analysis</h2>
            <p>Model Observations:
            {facial['model_observations']}</p>
            <p>Mock Observations Excluded:
            {facial['mock_observations_excluded']}</p>
            <p>Most Frequent Expression:
            {escape(str(facial['most_frequent_expression'] or 'N/A'))}</p>
        </div>

        <h2>Scenario Details</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Reference</th>
                <th>Spoken Response</th>
                <th>Verbal Emotion</th>
                <th>Evaluation</th>
                <th>Facial Expression</th>
                <th>Comparison</th>
            </tr>
            {rows}
        </table>

        <p class="note">
            Prototype report generated from predefined test scenarios.
            Mock facial observations are excluded from model results.
            This report is not a clinical assessment.
        </p>
    </body>
    </html>
    """

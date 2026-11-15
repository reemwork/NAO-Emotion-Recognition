"""Standalone MLLM benchmark script (NOT the live session classifier).

Loads predefined text test cases, sends them to the configured local
Ollama model, measures label agreement/latency, and writes CSV results.
This script creates image bytes but does NOT include them in the actual
Ollama request, so its current evaluation call is text-only.
"""

import json
import base64
import csv
import time
from pathlib import Path
from PIL import Image
from io import BytesIO
import requests


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
# Experimental model choice; the live backend selects Qwen separately.
MODEL = "gemma3:4b"

LABELS = {"Happy", "Sad", "Angry", "Neutral", "Unclear"}

with open(DATA / "scenarios.json", encoding="utf-8") as file:
    scenarios = {
        item["scenario_id"]: item
        for item in json.load(file)
    }

with open(DATA / "mllm_test_cases.json", encoding="utf-8") as file:
    test_cases = json.load(file)

results = []

for test in test_cases:
    scenario = scenarios[test["scenario_id"]]
    image_path = ROOT / scenario["image_path"]

    if not image_path.is_file():
        raise FileNotFoundError(f"Missing image: {image_path}")

    # Image is resized/encoded below but not passed in the HTTP payload.
    # Do not describe this specific test run as image+text inference.
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((448, 448))

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=80)

        image_data = base64.b64encode(
            buffer.getvalue()
        ).decode("utf-8")

    prompt = f"""
You are evaluating a child's verbal emotion recognition answer.

Identify the emotion communicated by the child's response.

Rules:
1. Classify explicit or indirectly described emotions as Happy, Sad, Angry, or Neutral.
2. Return Unclear if the response does not provide enough evidence to identify an emotion.
3. Neutral means an emotionally neutral expression, not an unknown answer.
4. Do not assume the child's answer is correct.
5. Base your classification only on the child's response.
6. Return exactly one label: Happy, Sad, Angry, Neutral, or Unclear.

Child's response: "{test['response']}"
"""

    # Time each request to compare runtime as well as label agreement.
    start = time.perf_counter()

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "think": False,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_ctx": 4096,
                    "num_predict": 256
                },
                "keep_alive": "10m"
            },
            timeout=180
        )

        response.raise_for_status()
        print("DONE REASON:", response.json().get("done_reason"))
        print("EVAL COUNT:", response.json().get("eval_count"))
        print("RAW MODEL RESPONSE:", repr(response.json()["message"]["content"]))
        print("THINKING:", repr(response.json()["message"].get("thinking")))

        prediction = response.json()["message"]["content"].strip()
        print("RAW MODEL RESPONSE:", repr(response.json()["message"]["content"]))
        print("THINKING:", repr(response.json()["message"].get("thinking")))
        prediction = prediction.strip(" .\n")

        if prediction not in LABELS:
            prediction = "Invalid Output"

    except requests.RequestException as error:
        prediction = "Error"
        print(f"Test {test['id']} failed: {error}")

    elapsed = round(time.perf_counter() - start, 2)
    passed = prediction == test["expected"]

    results.append({
        "test_id": test["id"],
        "scenario_id": test["scenario_id"],
        "reference_label": scenario["reference_label"],
        "child_response": test["response"],
        "expected": test["expected"],
        "predicted": prediction,
        "passed": passed,
        "response_time": elapsed
    })

    print(
        f"Test {test['id']}: "
        f"Expected={test['expected']} | "
        f"Predicted={prediction} | "
        f"Pass={passed} | "
        f"Time={elapsed}s",
        flush=True
    )

# Experiment results are separate from clinical or session reports.
output_file = DATA / "gemma3_4b_text_only_results.csv"

with open(output_file, "w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=results[0].keys())
    writer.writeheader()
    writer.writerows(results)

successful = [
    result for result in results
    if result["predicted"] in LABELS
]

correct = sum(result["passed"] for result in successful)

accuracy = (
    correct / len(results) * 100
    if results else 0
)

average_time = (
    sum(result["response_time"] for result in successful)
    / len(successful)
    if successful else 0
)

print("\n========== EVALUATION SUMMARY ==========")
print("Model:", MODEL)
print("Total Tests:", len(results))
print("Valid Predictions:", len(successful))
print("Correct Predictions:", correct)
print(f"Classification Accuracy: {accuracy:.2f}%")
print(f"Average Response Time: {average_time:.2f} seconds")
print("Results Saved To:", output_file)
print("========================================")

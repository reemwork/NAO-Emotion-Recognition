"""Earlier one-scenario image+text MLLM experiment (NOT production).

Passes the scenario image and a sample response to a local Qwen model.
The currently selected live classifier, backend.emotion_classifier,
intentionally receives text ONLY to avoid reference-image leakage.
"""

import json
import base64
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_FILE = PROJECT_ROOT / "data" / "scenarios.json"

with open(SCENARIOS_FILE, "r", encoding="utf-8") as file:
    scenarios = json.load(file)

scenario = scenarios[0]
image_path = PROJECT_ROOT / scenario["image_path"]

child_response = "He feels that way because he received a gift."
prompt = f"""
You are evaluating a child's verbal emotion recognition answer.

Identify the emotion communicated by the child's response.

Rules:
1. Classify explicit or indirectly described emotions as Happy, Sad, Angry, or Neutral.
2. Return Unclear if the response does not provide enough evidence to identify an emotion.
3. Neutral means an emotionally neutral expression, not an unknown answer.
4. Use the image only to understand references in the response.
5. Do not assume the child correctly identified the emotion shown in the image.
6. Return exactly one label: Happy, Sad, Angry, Neutral, or Unclear.

Child's response: "{child_response}"
"""

# This prototype DOES pass the image to Ollama for experimental comparison.
with open(image_path, "rb") as file:
    image_base64 = base64.b64encode(file.read()).decode("utf-8")

start_time = time.perf_counter()

response = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen2.5vl:3b",
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_base64]
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_ctx": 8192
        }
    },
    timeout=180
)

response.raise_for_status()

elapsed_time = time.perf_counter() - start_time

prediction = response.json()["message"]["content"].strip()

valid_labels = {"Happy", "Sad", "Angry", "Neutral", "Unclear"}

# Compare the model label against the predefined scenario reference.
# Unlike the live workflow, this prototype prompt has access to the image.
if prediction not in valid_labels:
    evaluation = "Invalid Output"
elif prediction == "Unclear":
    evaluation = "Unclear"
elif prediction == scenario["reference_label"]:
    evaluation = "Correct"
else:
    evaluation = "Incorrect"

print("\n========== MLLM RESULT ==========")
print("Scenario ID:", scenario["scenario_id"])
print("Image:", image_path.name)
print("Reference Label:", scenario["reference_label"])
print("Child's Answer:", child_response)
print("MLLM Prediction:", prediction)
print("Evaluation:", evaluation)
print(f"Response Time: {elapsed_time:.2f} seconds")
print("=================================")


import json
import requests

MODEL = "qwen2.5vl:3b"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

LABELS = ["Happy", "Sad", "Angry", "Neutral", "Unclear"]


def classify_emotion(spoken_text: str) -> str:
    if not spoken_text or not spoken_text.strip():
        raise ValueError("The spoken response cannot be empty.")

    prompt = """
You are an emotion classification system.

Your task is to identify the emotion described in
the user's verbal response.

Classify the response as exactly one of:
Happy, Sad, Angry, Neutral, or Unclear.

Classification rules:

1. Happy:
The response describes happiness, joy, smiling,
excitement, or other positive emotional expressions.

2. Sad:
The response describes sadness, crying,
disappointment, or other sad expressions.

3. Angry:
The response describes anger, frustration,
or other angry expressions.

4. Neutral:
The response explicitly describes a neutral,
calm, or emotionless expression.

5. Unclear:
The response does not provide enough information
to determine an emotion.

IMPORTANT:
- "I don't know" must be classified as Unclear.
- "I'm not sure" must be classified as Unclear.
- "I can't tell" must be classified as Unclear.
- Do NOT classify uncertainty as Neutral.
- Neutral is an actual emotional expression category.
- Do not assume that the response matches an image.
- Classify only the information in the response.
- If a response contains a recognizable emotion,
  use that evidence rather than assuming uncertainty.

Examples:
Input: "I don't know."
Output: Unclear

Input: "She looks calm and has a neutral expression."
Output: Neutral

Input: "He is crying."
Output: Sad

Input: "She is standing near a window."
Output: Unclear

Return only the requested JSON object.
"""


    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": spoken_text.strip()
                }
            ],
            "stream": False,
            "format": {
                "type": "object",
                "properties": {
                    "emotion": {
                        "type": "string",
                        "enum": LABELS
                    }
                },
                "required": ["emotion"],
                "additionalProperties": False
            },
            "options": {
                "temperature": 0,
                "num_predict": 64
            },
            "keep_alive": "10m"
        },
        timeout=180
    )

    response.raise_for_status()

    try:
        model_output = json.loads(
            response.json()["message"]["content"]
        )
        prediction = model_output["emotion"]

    except (KeyError, ValueError, TypeError) as error:
        raise RuntimeError(
            "Invalid response format from the MLLM."
        ) from error

    if prediction not in LABELS:
        raise RuntimeError(
            f"Invalid emotion label: {prediction}"
        )

    return prediction

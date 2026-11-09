import os
import glob
from deepface import DeepFace

image_folder = "data/nao_frames"

images = glob.glob(os.path.join(image_folder, "*.jpg"))

if not images:
    print("Error: No images found in data/nao_frames")
    exit()

image_name = max(images, key=os.path.getmtime)

print("Analyzing facial emotion...")
print("Image:", image_name)

try:
    results = DeepFace.analyze(
        img_path=image_name,
        actions=["emotion"]
    )

    if isinstance(results, list):
        result = results[0]
    else:
        result = results

    dominant_emotion = result["dominant_emotion"]

    print("\n========== RESULT ==========")
    print("Dominant emotion:", dominant_emotion)
    print("============================")

    print("\nEmotion scores:")
    for emotion, score in result["emotion"].items():
        print(f"- {emotion}: {score:.2f}%")

    text_file = os.path.splitext(image_name)[0] + ".txt"

    with open(text_file, "w", encoding="utf-8") as f:
        f.write("========== FACIAL EMOTION ANALYSIS ==========\n")
        f.write(f"Dominant emotion: {dominant_emotion}\n")
        f.write("=============================================\n\n")

        f.write("Emotion scores:\n")

        for emotion, score in result["emotion"].items():
            f.write(f"- {emotion}: {score:.2f}%\n")

    print("\nFull analysis saved to:", text_file)

except Exception as e:
    print("Error:", e)
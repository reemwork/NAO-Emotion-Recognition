import cv2
import requests
import os
from datetime import datetime


camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print("Could not open laptop camera.")
    exit()

print("Camera opened successfully!")
print("Press SPACE to capture a frame.")
print("Press Q to quit.")


while True:
    success, frame = camera.read()

    if not success:
        print("Could not read camera frame.")
        break

    cv2.imshow("Laptop Camera Test", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord(" "):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_filename = f"temp_frame_{timestamp}.jpg"

        cv2.imwrite(temp_filename, frame)

        try:
            with open(temp_filename, "rb") as image_file:
                response = requests.post(
                    "http://127.0.0.1:8000/api/camera/frame",
                    files={
                        "frame": (
                            temp_filename,
                            image_file,
                            "image/jpeg"
                        )
                    }
                )

            if response.status_code == 200:
                print("Frame sent to backend successfully!")
                print(response.json())
            else:
                print("Backend error:", response.status_code)
                print(response.text)

        except Exception as e:
            print("Frame upload failed:", e)

        finally:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    elif key == ord("q"):
        break


camera.release()
cv2.destroyAllWindows()
"""NAO camera and facial analysis API."""

from .api import (
    router,
    set_camera_target,
    clear_camera_target,
    upload_camera_frame,
    upload_raw_camera_frame,
    upload_session_frame,
    evaluate_facial_frame,
    save_facial_result,
    classify_facial_frame,
    FacialInferenceError,
)

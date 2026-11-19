
"""Professional still-image FER interface using pretrained ResMaskingNet (RMN).
No camera required. Supports Unicode Windows paths and exports PNG + JSON.
"""
import json
import math
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk, ImageDraw, ImageFont
from rmn import RMN

EMOTIONS = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']
NAMES = {'angry':'Angry', 'disgust':'Disgust', 'fear':'Fear', 'happy':'Happy',
         'sad':'Sad', 'surprise':'Surprise', 'neutral':'Neutral'}
COLORS = {'angry':'#e05a5a', 'disgust':'#aa70d6', 'fear':'#db9c51',
          'happy':'#36b79a', 'sad':'#6599d5', 'surprise':'#e7bd4f', 'neutral':'#8193a7'}
BG = '#101a2a'
PANEL = '#1a2940'
TEXT = '#f4f7fc'
MUTED = '#aebfd3'


def read_image(path):
    arr = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError('Could not read image. Choose a JPG or PNG file.')
    return img


def save_image(path, img):
    ext = Path(path).suffix.lower()
    if ext not in ('.png', '.jpg', '.jpeg'):
        ext = '.png'
    ok, data = cv2.imencode(ext, img)
    if not ok:
        raise ValueError('Could not encode output image.')
    data.tofile(str(path))


def number(x):
    try:
        f = float(x)
        return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def normalized_probabilities(raw):
    """Handle RMN versions with probability dict or ordered 7-value list."""
    source = raw.get('proba_list', raw.get('probabilities', raw.get('scores')))
    probs = {}
    if isinstance(source, dict):
        for key, value in source.items():
            name = str(key).strip().lower()
            if name in EMOTIONS:
                probs[name] = number(value)
    elif isinstance(source, (list, tuple, np.ndarray)):
        for i, value in enumerate(source[:len(EMOTIONS)]):
            probs[EMOTIONS[i]] = number(value)
    # Some releases expose emotion-specific probabilities as top-level fields.
    if not probs:
        for key in EMOTIONS:
            if key in raw:
                probs[key] = number(raw[key])
    if probs and max(probs.values()) > 1.00001:
        probs = {k: v / 100.0 for k, v in probs.items()}
    return {k: max(0.0, min(1.0, probs.get(k, 0.0))) for k in EMOTIONS}


def parse_face(raw, width, height):
    if not isinstance(raw, dict):
        raise ValueError('Unexpected face result from RMN.')
    label = str(raw.get('emo_label', raw.get('emotion', raw.get('label', 'unknown')))).lower().strip()
    probs = normalized_probabilities(raw)
    confidence = number(raw.get('emo_proba', raw.get('confidence', probs.get(label, 0.0))))
    if confidence > 1.00001:
        confidence /= 100.0
    if label not in EMOTIONS and probs:
        label = max(probs, key=probs.get)
        confidence = probs[label]
    if label in EMOTIONS and probs.get(label, 0) == 0 and confidence > 0:
        probs[label] = confidence
    box = raw.get('box', raw.get('bbox'))
    if all(k in raw for k in ('xmin', 'ymin', 'xmax', 'ymax')):
        coords = [raw['xmin'], raw['ymin'], raw['xmax'], raw['ymax']]
    elif isinstance(box, (list, tuple)) and len(box) >= 4:
        coords = list(box[:4])
    else:
        coords = [0, 0, 0, 0]
    x1, y1, x2, y2 = (int(number(v)) for v in coords)
    x1, x2 = sorted((max(0, min(width, x1)), max(0, min(width, x2))))
    y1, y2 = sorted((max(0, min(height, y1)), max(0, min(height, y2))))
    return {'emotion': label, 'confidence': round(max(0, min(1, confidence)), 5),
            'probabilities': {k: round(v, 5) for k, v in probs.items()},
            'bounding_box': {'xmin': x1, 'ymin': y1, 'xmax': x2, 'ymax': y2}}



def box_area(face):
    b = face['bounding_box']
    return max(0, b['xmax'] - b['xmin']) * max(0, b['ymax'] - b['ymin'])


def box_iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    intersection = max(0, x2-x1) * max(0, y2-y1)
    area_a = max(0, a[2]-a[0]) * max(0, a[3]-a[1])
    area_b = max(0, b[2]-b[0]) * max(0, b[3]-b[1])
    return intersection / max(1, area_a + area_b - intersection)


def single_face(image, raw_results):
    """Select ONE plausible full-face RMN detection, never combine emotion scores.

    OpenCV's frontal-face detector supplies a geometry reference only. The
    emotion and confidence always come from the selected RMN result.
    """
    height, width = image.shape[:2]
    candidates = []
    for raw in (raw_results or []):
        try:
            face = parse_face(raw, width, height)
        except (ValueError, TypeError, KeyError):
            continue
        if box_area(face) > 0:
            candidates.append(face)
    if not candidates:
        return None

    # Independent detector helps distinguish full faces from overlapping
    # partial boxes. Failure is harmless: fall back to the largest RMN box.
    reference = None
    try:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        if not cascade.empty():
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            detections = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5,
                minSize=(max(24, width // 12), max(24, height // 12))
            )
            if len(detections):
                x, y, w, h = max(detections, key=lambda d: d[2]*d[3])
                reference = (int(x), int(y), int(x+w), int(y+h))
    except cv2.error:
        pass

    if reference is not None:
        def score(face):
            b = face['bounding_box']
            coords = (b['xmin'], b['ymin'], b['xmax'], b['ymax'])
            return (box_iou(coords, reference), box_area(face))
        # A good geometric match is preferable to a smaller partial face.
        selected = max(candidates, key=score)
    else:
        selected = max(candidates, key=box_area)
    return selected


def annotate(image, faces):
    result = image.copy()
    for face in faces:
        b = face['bounding_box']
        x1, y1, x2, y2 = (b[k] for k in ('xmin', 'ymin', 'xmax', 'ymax'))
        if x2 <= x1 or y2 <= y1:
            continue
        color = (149, 217, 110)
        cv2.rectangle(result, (x1, y1), (x2, y2), color, 3)
        label = f"{NAMES.get(face['emotion'], 'Unknown')} {face['confidence']*100:.1f}%"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = max(.55, min(1.1, result.shape[1] / 950))
        (tw, th), base = cv2.getTextSize(label, font, scale, 2)
        y_top = max(0, y1 - th - 16)
        cv2.rectangle(result, (x1, y_top), (min(result.shape[1], x1+tw+14), y_top+th+14), color, -1)
        cv2.putText(result, label, (x1+7, y_top+th+6), font, scale, (18, 28, 40), 2, cv2.LINE_AA)
    return result


def export_report(image_path, image, faces):
    path = Path(image_path)
    base = path.with_name(path.stem + '_cv_result')
    png = base.with_suffix('.png')
    jsn = base.with_suffix('.json')
    status = 'no_face' if not faces else 'success'
    payload = {
        'model': 'ResMaskingNet (RMN pretrained)',
        'input_image': str(path),
        'created_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'status': status,
        'faces': faces,  # Always zero or one face in this single-face workflow.
        'note': 'Model confidence is not a measure of accuracy. Facial expression does not establish internal emotion.'
    }
    save_image(png, annotate(image, faces))
    jsn.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return png, jsn, status


class Application:
    def __init__(self, root):
        self.root = root
        root.title('Facial Expression Analysis | Computer Vision')
        root.configure(bg=BG)
        root.geometry('1100x760')
        root.minsize(850, 650)
        self.model = None
        self.photo = None
        self.image_path = None
        self.build()

    def label(self, parent, text, size=12, color=TEXT, bold=False, **kwargs):
        return tk.Label(parent, text=text, font=('Segoe UI', size, 'bold' if bold else 'normal'),
                        fg=color, bg=kwargs.pop('bg', BG), **kwargs)

    def build(self):
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill='x', padx=30, pady=(24, 14))
        self.label(head, 'FACIAL EXPRESSION ANALYSIS', 22, bold=True).pack(anchor='w')
        self.label(head, 'Pretrained ResMaskingNet  •  Still-image evaluation  •  No camera', 11, MUTED).pack(anchor='w', pady=(3, 0))
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill='x', padx=30, pady=(0, 15))
        tk.Button(top, text='  Choose image and analyze  ', command=self.analyze,
                  bg='#3c8eea', fg='white', activebackground='#2675c8',
                  activeforeground='white', relief='flat', padx=16, pady=11,
                  font=('Segoe UI', 12, 'bold'), cursor='hand2').pack(side='left')
        self.status = self.label(top, 'Ready to analyze an image', 11, MUTED)
        self.status.pack(side='left', padx=16)

        content = tk.Frame(self.root, bg=BG)
        content.pack(fill='both', expand=True, padx=30, pady=(0, 16))
        left = tk.Frame(content, bg=PANEL)
        left.pack(side='left', fill='both', expand=True, padx=(0, 14))
        self.label(left, 'IMAGE PREVIEW', 11, MUTED, bold=True, bg=PANEL).pack(anchor='w', padx=20, pady=(18, 10))
        self.preview = tk.Label(left, text='Select an image to begin', font=('Segoe UI', 14),
                                bg=PANEL, fg=MUTED)
        self.preview.pack(fill='both', expand=True, padx=14, pady=(0, 18))
        right = tk.Frame(content, bg=PANEL, width=370)
        right.pack(side='right', fill='y')
        right.pack_propagate(False)
        self.label(right, 'ANALYSIS RESULT', 11, MUTED, bold=True, bg=PANEL).pack(anchor='w', padx=20, pady=(18, 12))
        self.main_emotion = self.label(right, '—', 30, TEXT, bold=True, bg=PANEL)
        self.main_emotion.pack(anchor='w', padx=20)
        self.confidence = self.label(right, 'Choose an image', 15, MUTED, bg=PANEL)
        self.confidence.pack(anchor='w', padx=20, pady=(4, 8))
        self.face_status = self.label(right, '', 11, MUTED, bg=PANEL, wraplength=330, justify='left')
        self.face_status.pack(anchor='w', padx=20, pady=(0, 12))
        self.label(right, 'EMOTION PROBABILITIES', 11, MUTED, bold=True, bg=PANEL).pack(anchor='w', padx=20, pady=(6, 10))
        self.bars = {}
        for emotion in EMOTIONS:
            row = tk.Frame(right, bg=PANEL)
            row.pack(fill='x', padx=20, pady=5)
            self.label(row, NAMES[emotion], 10, TEXT, bg=PANEL, width=9, anchor='w').pack(side='left')
            canvas = tk.Canvas(row, width=178, height=15, bg='#2d3c50', highlightthickness=0)
            canvas.pack(side='left', padx=7)
            pct = self.label(row, '—', 10, MUTED, bg=PANEL, width=7, anchor='e')
            pct.pack(side='right')
            self.bars[emotion] = (canvas, pct)
        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill='x', padx=30, pady=(0, 20))
        self.files_label = self.label(foot, 'Output: annotated PNG + structured JSON saved beside the input image.', 10, MUTED, wraplength=1000, justify='left')
        self.files_label.pack(anchor='w')
        self.label(foot, 'Note: Confidence is not accuracy. Expression predictions are not a diagnosis or a measure of emotional understanding.',
                   10, MUTED, wraplength=1000, justify='left').pack(anchor='w', pady=(5, 0))

    def show_preview(self, bgr):
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        pil.thumbnail((610, 550), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(pil)
        self.preview.configure(image=self.photo, text='')

    def update_bars(self, probs):
        for emotion, (canvas, label) in self.bars.items():
            p = probs.get(emotion, 0)
            canvas.delete('all')
            canvas.create_rectangle(0, 0, int(178*p), 15, fill=COLORS[emotion], outline='')
            label.configure(text=f'{p*100:.1f}%')

    def analyze(self):
        path = filedialog.askopenfilename(title='Select a face image',
                    filetypes=[('Image files', '*.jpg *.jpeg *.png *.bmp'), ('All files', '*.*')])
        if not path:
            return
        self.image_path = path
        self.status.configure(text='Analyzing... (first run may download model weights)')
        self.root.update_idletasks()
        try:
            image = read_image(path)
            if self.model is None:
                self.model = RMN()
            raw = self.model.detect_emotion_for_single_frame(image)
            if raw is None:
                raw = []
            face = single_face(image, raw)
            faces = [face] if face is not None else []
            png, jsn, status = export_report(path, image, faces)
            self.show_preview(annotate(image, faces))
            if not faces:
                self.main_emotion.configure(text='No face detected', fg='#efc57c')
                self.confidence.configure(text='Try a clearer front-facing image')
                self.face_status.configure(text='No face detected in this image')
                self.update_bars({})
            else:
                face = faces[0]
                emo = face['emotion']
                self.main_emotion.configure(text=NAMES.get(emo, 'Unknown'), fg=COLORS.get(emo, TEXT))
                self.confidence.configure(text=f"Model confidence: {face['confidence']*100:.2f}%")
                self.face_status.configure(text='One face selected. The image and panel show the same prediction.')
                self.update_bars(face['probabilities'])
            self.status.configure(text='Analysis complete')
            self.files_label.configure(text=f'Saved image: {png}\nSaved JSON: {jsn}')
        except Exception as exc:
            self.status.configure(text='Analysis failed')
            messagebox.showerror('Analysis error', str(exc))


if __name__ == '__main__':
    root = tk.Tk()
    Application(root)
    root.mainloop()

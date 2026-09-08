#!/usr/bin/env python3
"""
VisionAssist V1 — Fusion Script with Live Stream
Camera → YOLO → Bounding-box distance estimation → Zone logic → TTS
Vision-based distance replaces PSoC radar. PSoC not required.
Live annotated video stream at http://<pi-ip>:5000
Live webapp at http://<pi-ip>:5000/app
"""

from picamera2 import Picamera2
from ultralytics import YOLO
import tts
import time
import threading
import cv2
import os
from flask import Flask, Response, jsonify, send_from_directory

# ── Configuration ───────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD   = 0.45
COOLDOWN_SECONDS       = 3.0
LOOP_DELAY             = 0.1
DETECTION_HOLD_SECONDS = 1.0

# ── Vision-based distance estimation ────────────────────────────────────────
# IMX708 → Mode 0 sensor crop (3072×1728 from 4608×2592 full sensor)
# → 1280×720 ISP output → 90° CCW software rotation → 720×1280 frame to YOLO.
# Focal length for the 1280px post-rotation height dimension ≈ 1435px.
FOCAL_LENGTH_PX = 900

# Typical real-world object heights in metres (COCO classes)
OBJECT_HEIGHTS_M = {
    "person":        1.70,
    "chair":         0.90,
    "couch":         0.90,
    "bed":           0.60,
    "dining table":  0.75,
    "toilet":        0.40,
    "refrigerator":  1.70,
    "oven":          0.90,
    "sink":          0.85,
    "car":           1.50,
    "truck":         2.50,
    "bus":           3.00,
    "bicycle":       1.10,
    "motorcycle":    1.10,
    "dog":           0.50,
    "cat":           0.30,
    "bottle":        0.25,
    "cup":           0.12,
    "laptop":        0.30,
    "tv":            0.60,
    "monitor":       0.50,
    "backpack":      0.50,
    "handbag":       0.30,
    "suitcase":      0.60,
    "umbrella":      0.90,
    "door":          2.00,
    "stairs":        1.00,
}
DEFAULT_HEIGHT_M = 1.0  # fallback for unrecognised classes

def estimate_distance_ft(label: str, bbox_h_px: int) -> float:
    """Estimate object distance in feet from bounding-box height."""
    if bbox_h_px <= 0:
        return 99.0
    real_h = OBJECT_HEIGHTS_M.get(label, DEFAULT_HEIGHT_M)
    distance_m = (real_h * FOCAL_LENGTH_PX) / bbox_h_px
    return distance_m * 3.28084

def ft_to_steps(distance_ft: float) -> int:
    """Convert feet to approximate walking steps (1 step ≈ 2.5 ft)."""
    return max(1, round(distance_ft / 2.5))

# ── Distance Zones ──────────────────────────────────────────────────────────
ZONE_SAFE    = "safe"
ZONE_CAUTION = "caution"
ZONE_WARNING = "warning"

def get_zone(distance_ft: float) -> str:
    if distance_ft > 9.0:
        return ZONE_SAFE
    elif distance_ft >= 6.0:
        return ZONE_CAUTION
    else:
        return ZONE_WARNING

# ── Object Risk Tiers ───────────────────────────────────────────────────────
HIGH_RISK = {
    "chair", "couch", "bed", "dining table", "toilet", "door",
    "wall", "stairs", "refrigerator", "oven", "sink"
}
MEDIUM_RISK = {
    "person", "dog", "cat", "bicycle", "motorcycle", "car"
}
DETECTION_BLOCKLIST = {
    "donut", "pizza", "cake", "hot dog", "banana",
    "broccoli", "carrot", "sandwich", "apple", "orange",
    "frisbee", "skis", "snowboard", "kite", "surfboard",
    "baseball bat", "baseball glove",
}

def get_risk(label: str) -> str:
    if label in HIGH_RISK:   return "high"
    if label in MEDIUM_RISK: return "medium"
    return "low"

def build_message(label: str, zone: str, risk: str, distance_ft: float) -> str | None:
    """Build TTS message for Pi earbuds — subject + steps, no zone jargon."""
    if risk == "low" and zone == ZONE_CAUTION:
        return None
    steps = ft_to_steps(distance_ft)
    step_word = "step" if steps == 1 else "steps"
    if zone == ZONE_WARNING:
        return f"stop, {label}, {steps} {step_word} ahead"
    elif zone == ZONE_CAUTION:
        return f"{label}, {steps} {step_word} ahead"
    return None

# ── Shared state ────────────────────────────────────────────────────────────
latest_frame       = None
frame_lock         = threading.Lock()
# subject: dict with label/distance_ft/steps/zone for the top detection only,
# or None when nothing is detected. Phone webapp reads this via /detections.
app_detection_data = {"labels": [], "subject": None}
app_detection_lock = threading.Lock()

app        = Flask(__name__)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Overlay ─────────────────────────────────────────────────────────────────
def draw_overlay(frame, boxes_with_dist, zone, display_distance, held=False):
    annotated   = frame.copy()
    zone_colors = {
        ZONE_SAFE:    (0, 200, 0),
        ZONE_CAUTION: (0, 165, 255),
        ZONE_WARNING: (0, 0, 255),
    }
    color = zone_colors.get(zone, (255, 255, 255))

    for (label, conf, risk, dist_ft, x1, y1, x2, y2) in boxes_with_dist:
        box_color = {"high": (0, 0, 255), "medium": (0, 165, 255), "low": (0, 200, 0)}[risk]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)
        steps = ft_to_steps(dist_ft)
        cv2.putText(annotated, f"{label} {conf:.0%} {dist_ft:.1f}ft (~{steps}s)",
                    (x1, max(y1 - 8, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2)

    # Header bar — 70px tall, two lines
    cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 70), (0, 0, 0), -1)
    held_text = " [held]" if held else ""
    # Line 1: distance in feet + zone
    cv2.putText(annotated, f"Dist: {display_distance:.1f} ft",
                (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2)
    cv2.putText(annotated, f"Zone: {zone.upper()}{held_text}",
                (240, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2)
    # Line 2: steps estimate
    steps = ft_to_steps(display_distance)
    step_word = "step" if steps == 1 else "steps"
    cv2.putText(annotated, f"~{steps} {step_word} ahead",
                (12, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (160, 160, 160), 2)
    return annotated

# ── Flask ───────────────────────────────────────────────────────────────────
def generate_frames():
    global latest_frame
    while True:
        with frame_lock:
            frame = latest_frame
        if frame is None:
            time.sleep(0.05)
            continue
        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        time.sleep(0.04)

@app.route('/')
def index():
    return '''
    <html><head><title>VisionAssist Live</title></head>
    <body style="background:#111;margin:0;display:flex;flex-direction:column;align-items:center;">
    <h2 style="color:#fff;font-family:monospace;margin:10px">VisionAssist — Live Feed</h2>
    <img src="/video" style="width:100%;max-width:960px;height:auto;border:2px solid #333">
    </body></html>
    '''

@app.route('/video')
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/app')
def webapp():
    return send_from_directory(SCRIPT_DIR, 'app.html')

@app.route('/detections')
def detections():
    with app_detection_lock:
        data = {
            "labels":  list(app_detection_data["labels"]),
            "subject": dict(app_detection_data["subject"])
                       if app_detection_data["subject"] else None,
        }
    return jsonify(data)

# ── Main loop ───────────────────────────────────────────────────────────────
def main():
    global latest_frame

    print("Loading YOLOv8n model...")
    model = YOLO("yolov8n.pt")

    print("Initializing camera...")
    picam2 = Picamera2()
    config = picam2.create_still_configuration(
        main={"size": (1280, 720), "format": "RGB888"}
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(2)

    flask_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    print("Live stream at http://<pi-ip>:5000")
    print("Webapp     at http://<pi-ip>:5000/app")

    tts.speak("Vision Assist starting up")
    print("\n--- Running. Press Ctrl+C to stop. ---\n")

    last_spoken_message  = None
    last_spoken_time     = 0
    last_detections      = []
    last_boxes_with_dist = []
    last_detection_time  = 0

    while True:
        frame = picam2.capture_array()
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        results = model(frame, verbose=False)
        boxes   = results[0].boxes

        current_detections      = []
        current_boxes_with_dist = []
        for b in boxes:
            if float(b.conf) < CONFIDENCE_THRESHOLD:
                continue
            label = model.names[int(b.cls)]
            if label in DETECTION_BLOCKLIST:
                continue
            conf  = float(b.conf)
            risk  = get_risk(label)
            x1, y1, x2, y2 = map(int, b.xyxy[0])
            dist_ft = estimate_distance_ft(label, y2 - y1)
            current_detections.append((label, conf, risk, dist_ft))
            current_boxes_with_dist.append((label, conf, risk, dist_ft, x1, y1, x2, y2))

        now = time.time()

        # Detection persistence
        if current_detections:
            last_detections      = current_detections
            last_boxes_with_dist = current_boxes_with_dist
            last_detection_time  = now
            detections      = current_detections
            boxes_with_dist = current_boxes_with_dist
            held = False
        elif (now - last_detection_time) < DETECTION_HOLD_SECONDS:
            detections      = last_detections
            boxes_with_dist = last_boxes_with_dist
            held = True
        else:
            detections      = []
            boxes_with_dist = []
            held = False

        # Sort: highest risk first, then closest within tier
        detections.sort(key=lambda d: ({"high": 0, "medium": 1, "low": 2}[d[2]], d[3]))

        if detections:
            top_label, top_conf, top_risk, top_dist = detections[0]
            zone             = get_zone(top_dist)
            display_distance = top_dist
        else:
            top_label = top_conf = top_risk = top_dist = None
            zone             = ZONE_SAFE
            display_distance = 99.0

        # Update shared state — subject only (top detection after sort)
        with app_detection_lock:
            if detections:
                steps = ft_to_steps(top_dist)
                app_detection_data["labels"]  = [top_label]
                app_detection_data["subject"] = {
                    "label":       top_label,
                    "distance_ft": round(top_dist, 1),
                    "steps":       steps,
                    "zone":        zone,
                }
            else:
                app_detection_data["labels"]  = []
                app_detection_data["subject"] = None

        annotated = draw_overlay(frame, boxes_with_dist, zone, display_distance, held)
        with frame_lock:
            latest_frame = annotated

        print(f"[{time.strftime('%H:%M:%S')}] "
              f"Zone: {zone.upper():7s} | "
              f"{'[HELD] ' if held else ''}"
              f"Detections: {[(l, f'{c:.0%}', f'{d:.1f}ft', r) for l,c,r,d in detections]}")

        if zone == ZONE_SAFE or not detections:
            last_spoken_message = None
        else:
            message         = build_message(top_label, zone, top_risk, top_dist)
            time_since_last = now - last_spoken_time
            if message and (message != last_spoken_message or time_since_last >= COOLDOWN_SECONDS):
                tts.speak(message)
                last_spoken_message = message
                last_spoken_time    = now

        time.sleep(LOOP_DELAY)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped by user.")

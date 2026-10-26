import cv2
import time
import threading
import os
import sys
import requests
import numpy as np
import serial
import mss
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from detector import VisionDetector

app = Flask(__name__, static_folder="captures")
CORS(app)

CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

# Configuration & State
config = {
    "source_type": "standby",   # Defaults to standby to prevent accidental screen/camera disclosure
    "com_port": "COM9",
    "baud_rate": 921600,
    "esp32_ip": "192.168.4.1",
    "webcam_index": 0,
    "flash_state": False,
    "flash_brightness": 255,
    "auto_capture_motion": False,
    "last_motion_capture_time": 0
}

detector = VisionDetector()
latest_raw_frame = None
latest_processed_frame = None
latest_ai_jpeg = None
latest_raw_jpeg = None
latest_stats = {}
last_frame_time = 0
lock = threading.Lock()
ser_instance = None
ser_lock = threading.Lock()
current_serial_port = None
current_serial_baud = None

# Truthful connection telemetry
selected_source = "standby"
active_source = None
source_connected = False
source_error = "Standby mode active"

import platform
IS_WINDOWS = platform.system() == "Windows"

def open_webcam(index):
    if IS_WINDOWS:
        try:
            c = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if c.isOpened():
                return c
        except Exception:
            pass
    return cv2.VideoCapture(index)

def release_source_resources(cap=None, stream_response=None, ser=None):
    """Cleanly close and release camera handles, HTTP streams, and serial ports."""
    if cap is not None:
        try:
            cap.release()
        except Exception:
            pass
    if stream_response is not None:
        try:
            stream_response.close()
        except Exception:
            pass
    if ser is not None:
        try:
            with ser_lock:
                ser.close()
        except Exception:
            pass

def get_serial_connection():
    global ser_instance, current_serial_port, current_serial_baud
    with ser_lock:
        target_port = config["com_port"]
        target_baud = config["baud_rate"]
        if ser_instance is not None:
            if not ser_instance.is_open or current_serial_port != target_port or current_serial_baud != target_baud:
                try:
                    ser_instance.close()
                except Exception:
                    pass
                ser_instance = None
        if ser_instance is None:
            try:
                ser_instance = serial.Serial(target_port, target_baud, timeout=0.05)
                ser_instance.dtr = False
                ser_instance.rts = False
                current_serial_port = target_port
                current_serial_baud = target_baud
                time.sleep(0.05)
            except Exception:
                ser_instance = None
        return ser_instance

def send_serial_cmd(cmd_str):
    with ser_lock:
        if ser_instance and ser_instance.is_open:
            try:
                ser_instance.write((cmd_str + "\n").encode())
                return True
            except Exception:
                return False
        return False

def get_esp32_host():
    raw = config["esp32_ip"].strip()
    if raw.startswith("http://"):
        raw = raw[7:]
    elif raw.startswith("https://"):
        raw = raw[8:]
    raw = raw.split("/")[0]
    return raw.split(":")[0]

def get_esp32_stream_url():
    host = get_esp32_host()
    return f"http://{host}:81/stream?key=argus_secure_key"

sct_instance = None

def generate_standby_frame(status_text="STANDBY / NO CAMERA CONNECTED", sub_text=""):
    w, h = 640, 480
    frame = np.full((h, w, 3), 16, dtype=np.uint8)

    # Grid background lines for professional telemetry look
    for x in range(0, w, 40):
        cv2.line(frame, (x, 0), (x, h), (26, 26, 32), 1)
    for y in range(0, h, 40):
        cv2.line(frame, (0, y), (w, y), (26, 26, 32), 1)

    # Center crosshair and badge box
    cv2.circle(frame, (w // 2, h // 2), 60, (0, 160, 220), 1)
    cv2.line(frame, (w // 2 - 80, h // 2), (w // 2 + 80, h // 2), (0, 160, 220), 1)
    cv2.line(frame, (w // 2, h // 2 - 80), (w // 2, h // 2 + 80), (0, 160, 220), 1)

    # Status text
    cv2.putText(frame, "ARGUS VISION", (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 180), 2)
    cv2.putText(frame, status_text, (30, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
    if sub_text:
        cv2.putText(frame, sub_text, (30, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 160), 1)

    # Time stamp footer
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    cv2.putText(frame, ts, (30, h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (90, 100, 110), 1)
    return frame

def generate_simulated_frame(message="SIMULATED RADAR FEED"):
    w, h = 640, 480
    frame = np.full((h, w, 3), 12, dtype=np.uint8)

    # Animated radar sweep
    cx, cy = w // 2, h // 2
    radius = 160
    cv2.circle(frame, (cx, cy), radius, (0, 180, 120), 1)
    cv2.circle(frame, (cx, cy), radius // 2, (0, 100, 70), 1)

    angle = (time.time() * 90) % 360
    rad = np.radians(angle)
    sweep_x = int(cx + radius * np.cos(rad))
    sweep_y = int(cy + radius * np.sin(rad))
    cv2.line(frame, (cx, cy), (sweep_x, sweep_y), (0, 255, 170), 2)

    # Simulated targets
    target_angles = [45, 160, 270]
    for ta in target_angles:
        trad = np.radians(ta)
        tx = int(cx + (radius * 0.7) * np.cos(trad))
        ty = int(cy + (radius * 0.7) * np.sin(trad))
        cv2.circle(frame, (tx, ty), 4, (0, 220, 255), -1)

    cv2.putText(frame, "SIMULATOR ACTIVE", (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 170), 2)
    cv2.putText(frame, message, (30, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 220, 200), 1)
    ts = time.strftime("%H:%M:%S", time.gmtime())
    cv2.putText(frame, f"REC // {ts}", (w - 180, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 1)
    return frame

def get_current_telemetry():
    """Returns accurate connection and source telemetry."""
    with lock:
        res = dict(latest_stats)
        res["selected_source"] = config.get("source_type", "standby")
        res["active_source"] = active_source
        res["connected"] = bool(source_connected)
        res["source_error"] = source_error
        res["source"] = config.get("source_type", "standby")
        res["last_frame_age"] = round(time.time() - last_frame_time, 2) if last_frame_time else None
        res["esp32_ip"] = config.get("esp32_ip")
        res["com_port"] = config.get("com_port")
    return res

def video_capture_worker():
    global latest_raw_frame, latest_processed_frame, latest_stats, last_frame_time
    global sct_instance, active_source, source_connected, source_error, selected_source
    cap = None
    last_source = None
    stream_response = None
    stream_bytes = b''
    sync_header = b'\xff\xaa\x55\xff'
    serial_buf = b''

    while True:
        try:
            curr_source = config.get("source_type", "standby")
            selected_source = curr_source
            frame = None

            # Handle source transition cleanly
            if curr_source != last_source:
                release_source_resources(cap, stream_response, ser_instance)
                cap = None
                stream_response = None
                serial_buf = b''
                stream_bytes = b''
                detector.reset_motion_history()
                last_source = curr_source
                last_frame_time = 0

            if curr_source == "standby":
                active_source = None
                source_connected = False
                source_error = "Standby mode - camera capture inactive"

            elif curr_source == "usb_serial":
                ser = get_serial_connection()
                if ser and ser.is_open:
                    try:
                        n = ser.in_waiting
                        chunk = ser.read(n if n > 0 else 1024)
                        if chunk:
                            serial_buf += chunk
                            if len(serial_buf) > 300000:
                                serial_buf = serial_buf[-100000:]

                            while True:
                                idx = serial_buf.find(sync_header)
                                if idx == -1:
                                    if len(serial_buf) > 3:
                                        serial_buf = serial_buf[-3:]
                                    break
                                
                                if idx > 0:
                                    serial_buf = serial_buf[idx:]
                                    idx = 0

                                if len(serial_buf) < 8:
                                    break

                                frame_len = int.from_bytes(serial_buf[4:8], byteorder='little')
                                if frame_len > 100000 or frame_len < 400:
                                    serial_buf = serial_buf[4:]
                                    continue

                                if len(serial_buf) < 8 + frame_len:
                                    break

                                jpeg_bytes = serial_buf[8:8+frame_len]
                                serial_buf = serial_buf[8+frame_len:]

                                if jpeg_bytes.startswith(b'\xff\xd8') and jpeg_bytes.endswith(b'\xff\xd9'):
                                    decoded = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                                    if decoded is not None:
                                        frame = decoded
                                        last_frame_time = time.time()
                                        active_source = "usb_serial"
                                        source_connected = True
                                        source_error = None
                    except Exception as e:
                        source_error = f"Serial read error: {e}"
                else:
                    source_error = f"Serial port {config['com_port']} closed or unavailable"

            elif curr_source == "esp32_wifi":
                url = get_esp32_stream_url()
                try:
                    if stream_response is None:
                        stream_response = requests.get(url, stream=True, timeout=2.0)
                        stream_bytes = b''

                    if stream_response.status_code == 200:
                        chunk = stream_response.raw.read(4096)
                        if chunk:
                            stream_bytes += chunk
                            a = stream_bytes.find(b'\xff\xd8')
                            b = stream_bytes.find(b'\xff\xd9')
                            if a != -1 and b != -1 and b > a:
                                jpg = stream_bytes[a:b+2]
                                stream_bytes = stream_bytes[b+2:]
                                decoded = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                                if decoded is not None:
                                    frame = decoded
                                    last_frame_time = time.time()
                                    active_source = "esp32_wifi"
                                    source_connected = True
                                    source_error = None
                        else:
                            stream_response = None
                    else:
                        source_error = f"ESP32 HTTP status {stream_response.status_code}"
                        stream_response = None
                except Exception as e:
                    source_error = f"ESP32 stream unreachable ({e})"
                    stream_response = None

            elif curr_source == "screen":
                try:
                    if sct_instance is None:
                        sct_instance = mss.mss()
                    mon = sct_instance.monitors[1] if len(sct_instance.monitors) > 1 else sct_instance.monitors[0]
                    sct_img = sct_instance.grab(mon)
                    raw_screen = np.array(sct_img)
                    bgr = cv2.cvtColor(raw_screen, cv2.COLOR_BGRA2BGR)
                    h, w = bgr.shape[:2]
                    target_w = 640
                    target_h = int(h * (target_w / w))
                    frame = cv2.resize(bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)
                    last_frame_time = time.time()
                    active_source = "screen"
                    source_connected = True
                    source_error = None
                except Exception as e:
                    sct_instance = None
                    source_error = f"Screen capture error: {e}"

            elif curr_source == "simulated":
                frame = generate_simulated_frame("SYNTHETIC SENSOR FEED")
                last_frame_time = time.time()
                active_source = "simulated"
                source_connected = True
                source_error = None

            elif curr_source == "webcam":
                if cap is None:
                    cap = open_webcam(config["webcam_index"])
                
                success, f = cap.read() if cap and cap.isOpened() else (False, None)
                if success and f is not None:
                    frame = f
                    last_frame_time = time.time()
                    active_source = "webcam"
                    source_connected = True
                    source_error = None
                else:
                    source_error = f"Webcam index {config['webcam_index']} failed to capture"

            # Check signal timeout: NO SILENT SCREEN FALLBACK
            now = time.time()
            if curr_source != "standby" and (now - last_frame_time > 1.8):
                source_connected = False
                active_source = None
                if not source_error:
                    source_error = f"Signal lost from {curr_source}"

            if frame is not None:
                annotated, stats = detector.process_frame(frame)
                stats["connected"] = True
                stats["selected_source"] = curr_source
                stats["active_source"] = curr_source
                stats["source"] = curr_source
                stats["source_error"] = None
                stats["esp32_ip"] = config["esp32_ip"]
                stats["com_port"] = config["com_port"]

                if config["auto_capture_motion"] and stats.get("motion_detected"):
                    if now - config["last_motion_capture_time"] > 3.0:
                        config["last_motion_capture_time"] = now
                        filename = f"motion_alert_{int(now)}.jpg"
                        filepath = os.path.join(CAPTURES_DIR, filename)
                        cv2.imwrite(filepath, annotated)

                _, buf_ai = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                _, buf_raw = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])

                with lock:
                    latest_raw_frame = frame
                    latest_processed_frame = annotated
                    latest_ai_jpeg = buf_ai.tobytes()
                    latest_raw_jpeg = buf_raw.tobytes()
                    latest_stats = stats
            else:
                # Provide an explicit standby card on the video stream
                status_title = f"{curr_source.upper()}: DISCONNECTED" if curr_source != "standby" else "STANDBY / NO SOURCE"
                sub_title = source_error or "Select a live camera source"
                standby_card = generate_standby_frame(status_title, sub_title)
                _, buf_ai = cv2.imencode('.jpg', standby_card, [cv2.IMWRITE_JPEG_QUALITY, 80])
                _, buf_raw = cv2.imencode('.jpg', standby_card, [cv2.IMWRITE_JPEG_QUALITY, 80])
                with lock:
                    latest_raw_frame = standby_card
                    latest_processed_frame = standby_card
                    latest_ai_jpeg = buf_ai.tobytes()
                    latest_raw_jpeg = buf_raw.tobytes()
                    latest_stats["connected"] = False
                    latest_stats["selected_source"] = curr_source
                    latest_stats["active_source"] = None
                    latest_stats["source"] = curr_source
                    latest_stats["source_error"] = source_error
                    latest_stats["fps"] = 0
                    latest_stats["detections"] = 0

            time.sleep(0.005)
        except Exception as e:
            source_error = f"Pipeline loop error: {e}"
            time.sleep(0.02)

thread = threading.Thread(target=video_capture_worker, daemon=True)
thread.start()

def stream_generator(use_ai=True):
    while True:
        with lock:
            jpeg_bytes = latest_ai_jpeg if use_ai else latest_raw_jpeg
            if jpeg_bytes is None:
                standby = generate_standby_frame("INITIALIZING STREAM...")
                _, buffer = cv2.imencode('.jpg', standby, [cv2.IMWRITE_JPEG_QUALITY, 80])
                jpeg_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
        time.sleep(0.025)

@app.route('/video_feed')
def video_feed():
    res = Response(stream_generator(use_ai=True),
                   mimetype='multipart/x-mixed-replace; boundary=frame')
    res.headers['Access-Control-Allow-Origin'] = '*'
    res.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return res

@app.route('/raw_feed')
def raw_feed():
    res = Response(stream_generator(use_ai=False),
                   mimetype='multipart/x-mixed-replace; boundary=frame')
    res.headers['Access-Control-Allow-Origin'] = '*'
    res.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return res

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify(get_current_telemetry())

VALID_SOURCES = {"standby", "screen", "webcam", "usb_serial", "esp32_wifi", "simulated"}
VALID_MODES = {"face", "gesture", "objects", "object", "motion", "edges", "edge", "night_vision", "night", "raw"}
MODE_ALIASES = {
    "object": "objects",
    "edge": "edges",
    "night": "night_vision"
}

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        data = request.json or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "error": "Request body must be a JSON object"}), 400

        if "source_type" in data:
            st = str(data["source_type"]).strip().lower()
            if st not in VALID_SOURCES:
                return jsonify({"success": False, "error": f"Invalid source_type '{st}'. Allowed: {sorted(list(VALID_SOURCES))}"}), 400
            config["source_type"] = st

        if "esp32_ip" in data:
            raw_ip = str(data["esp32_ip"]).strip()
            # Prevent link-local/cloud metadata SSRF
            if raw_ip.startswith("169.254."):
                return jsonify({"success": False, "error": "Link-local / metadata addresses are forbidden"}), 400
            config["esp32_ip"] = raw_ip

        if "com_port" in data:
            config["com_port"] = str(data["com_port"]).strip()

        if "mode" in data:
            m = str(data["mode"]).strip().lower()
            if m not in VALID_MODES:
                return jsonify({"success": False, "error": f"Invalid mode '{m}'. Allowed: {sorted(list(VALID_MODES))}"}), 400
            detector.mode = MODE_ALIASES.get(m, m)

        if "motion_threshold" in data:
            try:
                mt = int(data["motion_threshold"])
                if mt < 1 or mt > 255:
                    return jsonify({"success": False, "error": "motion_threshold must be between 1 and 255"}), 400
                detector.motion_threshold = mt
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "motion_threshold must be an integer"}), 400

        if "min_contour_area" in data:
            try:
                mca = int(data["min_contour_area"])
                if mca < 10 or mca > 50000:
                    return jsonify({"success": False, "error": "min_contour_area must be between 10 and 50000"}), 400
                detector.min_contour_area = mca
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "min_contour_area must be an integer"}), 400

        if "auto_capture_motion" in data:
            config["auto_capture_motion"] = bool(data["auto_capture_motion"])

        return jsonify({"success": True, "config": config, "mode": detector.mode})

    return jsonify({"config": config, "mode": detector.mode})

@app.route('/api/flash', methods=['POST'])
def trigger_flash():
    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Request body must be a JSON object"}), 400

    state = bool(data.get("state", not config["flash_state"]))
    try:
        brightness = int(data.get("brightness", config["flash_brightness"]))
        brightness = max(0, min(255, brightness))
    except (ValueError, TypeError):
        brightness = 255

    curr_source = config.get("source_type")
    if curr_source == "usb_serial":
        ser = get_serial_connection()
        if not ser or not ser.is_open:
            return jsonify({"success": False, "error": f"Serial port {config['com_port']} is not connected"}), 503
        cmd = f"LB{brightness}" if state else "L0"
        ok = send_serial_cmd(cmd)
        if not ok:
            return jsonify({"success": False, "error": "Failed to transmit command to serial port"}), 502
    elif curr_source == "esp32_wifi":
        try:
            host = get_esp32_host()
            url = f"http://{host}/led?state={1 if state else 0}&brightness={brightness}&key=argus_secure_key"
            resp = requests.get(url, timeout=1.5)
            if resp.status_code != 200:
                return jsonify({"success": False, "error": f"ESP32 returned status {resp.status_code}"}), 502
        except Exception as e:
            return jsonify({"success": False, "error": f"ESP32 camera unreachable ({e})"}), 502
    else:
        return jsonify({"success": False, "error": "Flash LED is only available when an ESP32 camera is connected"}), 400

    config["flash_state"] = state
    config["flash_brightness"] = brightness
    return jsonify({"success": True, "state": state, "brightness": brightness, "acknowledged": True})

import uuid

@app.route('/api/capture', methods=['POST'])
def manual_capture():
    with lock:
        frame = latest_processed_frame
    if frame is not None:
        filename = f"capture_{int(time.time())}_{uuid.uuid4().hex[:6]}.jpg"
        filepath = os.path.join(CAPTURES_DIR, filename)
        written = cv2.imwrite(filepath, frame)
        if not written:
            return jsonify({"success": False, "error": "Failed to write capture to disk"}), 500
        return jsonify({"success": True, "filename": filename, "url": f"/captures/{filename}"})
    return jsonify({"success": False, "error": "No frame available"}), 500

@app.route('/api/captures', methods=['GET'])
def list_captures():
    files = []
    try:
        entries = sorted(os.listdir(CAPTURES_DIR), reverse=True)
    except Exception:
        entries = []
    for f in entries:
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            filepath = os.path.join(CAPTURES_DIR, f)
            try:
                files.append({
                    "filename": f,
                    "url": f"/captures/{f}",
                    "size_kb": round(os.path.getsize(filepath) / 1024, 1),
                    "timestamp": os.path.getmtime(filepath)
                })
            except OSError:
                continue
    return jsonify(files)

@app.route('/captures/<path:filename>')
def serve_capture(filename):
    safe_name = os.path.basename(filename)
    return send_from_directory(CAPTURES_DIR, safe_name)

@app.route('/api/captures/<path:filename>', methods=['DELETE'])
def delete_capture(filename):
    safe_name = os.path.basename(filename)
    filepath = os.path.join(CAPTURES_DIR, safe_name)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            return jsonify({"success": True, "message": f"{safe_name} deleted"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "File not found"}), 404

@app.route('/api/captions', methods=['GET', 'POST'])
def handle_captions():
    if request.method == 'POST':
        data = request.json or {}
        if data.get('action') == 'clear':
            detector.clear_captions()
            return jsonify({"success": True, "message": "Captions cleared"})
    
    return jsonify({
        "current_sentence": detector.current_sentence or " ".join(detector.caption_words),
        "words": list(detector.caption_words),
        "last_committed": detector.last_committed_word,
        "history": list(detector.sentence_history[-10:]),
        "has_live_hand": detector.latest_landmarks_vector is not None
    })

@app.route('/api/train_gesture', methods=['POST'])
def train_gesture():
    data = request.json or {}
    phrase = data.get("phrase", "").strip().upper()
    vector = data.get("vector") or detector.latest_landmarks_vector

    if not phrase:
        return jsonify({"success": False, "error": "Sign/Phrase name is required"}), 400
    if not vector or len(vector) != 63:
        return jsonify({"success": False, "error": "No hand landmark vector available. Hold your hand in front of the camera first."}), 400

    ok = detector.save_custom_gesture(phrase, vector)
    return jsonify({
        "success": ok,
        "phrase": phrase,
        "saved_gestures": list(detector.custom_gestures.keys())
    })

if __name__ == '__main__':
    host = os.environ.get("ARGUS_HOST", "127.0.0.1")
    port = int(os.environ.get("ARGUS_PORT", 5000))
    app.run(host=host, port=port, threaded=True, debug=False)

import cv2
import time
import threading
import os
import requests
import numpy as np
import serial
import mss
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from detector import VisionDetector

app = Flask(__name__, static_folder="captures")
CORS(app)

CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

# Configuration & State
config = {
    "source_type": "screen",   # Defaults to laptop screen for real optical stream
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
            except Exception:
                pass

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
    return f"http://{host}:81/stream"

sct_instance = None

def generate_simulated_frame(message="STANDBY..."):
    w, h = 640, 480
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.putText(frame, message, (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 180), 2)
    return frame

def video_capture_worker():
    global latest_raw_frame, latest_processed_frame, latest_stats, last_frame_time, sct_instance
    cap = None
    last_source = None
    stream_response = None
    stream_bytes = b''
    sync_header = b'\xff\xaa\x55\xff'
    serial_buf = b''

    while True:
        try:
            curr_source = config["source_type"]
            frame = None

            if curr_source == "usb_serial":
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
                    except Exception:
                        pass

            elif curr_source == "esp32_wifi":
                url = get_esp32_stream_url()
                try:
                    if stream_response is None or last_source != "esp32_wifi":
                        last_source = "esp32_wifi"
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
                                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                                if frame is not None:
                                    last_frame_time = time.time()
                        else:
                            stream_response = None
                    else:
                        stream_response = None
                except Exception:
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
                except Exception:
                    sct_instance = None

            elif curr_source == "simulated":
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
                except Exception:
                    sct_instance = None

            elif curr_source == "webcam":
                if cap is None or last_source != "webcam":
                    if cap:
                        cap.release()
                    cap = open_webcam(config["webcam_index"])
                    last_source = "webcam"
                
                success, f = cap.read() if cap and cap.isOpened() else (False, None)
                if success and f is not None:
                    frame = f
                    last_frame_time = time.time()
                else:
                    if cap:
                        cap.release()
                    cap = cv2.VideoCapture(config["webcam_index"])
                    success, f = cap.read() if cap and cap.isOpened() else (False, None)
                    if success and f is not None:
                        frame = f
                        last_frame_time = time.time()

            # If selected hardware source has no camera connected, gracefully fallback to laptop screen
            if frame is None and (time.time() - last_frame_time > 2.0):
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
                except Exception:
                    sct_instance = None

            is_conn = (time.time() - last_frame_time) < 1.5

            if frame is not None:
                annotated, stats = detector.process_frame(frame)
                stats["connected"] = is_conn
                stats["source"] = curr_source
                stats["esp32_ip"] = config["esp32_ip"]
                stats["com_port"] = config["com_port"]

                if config["auto_capture_motion"] and stats.get("motion_detected"):
                    now = time.time()
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
                if not is_conn:
                    with lock:
                        latest_stats["connected"] = False

            time.sleep(0.005)
        except Exception:
            time.sleep(0.02)

thread = threading.Thread(target=video_capture_worker, daemon=True)
thread.start()

def stream_generator(use_ai=True):
    while True:
        with lock:
            jpeg_bytes = latest_ai_jpeg if use_ai else latest_raw_jpeg
            if jpeg_bytes is None:
                standby = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(standby, "INITIALIZING STREAM...", (140, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 180), 2)
                _, buffer = cv2.imencode('.jpg', standby, [cv2.IMWRITE_JPEG_QUALITY, 80])
                jpeg_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
        time.sleep(0.025)

@app.route('/video_feed')
def video_feed():
    return Response(stream_generator(use_ai=True),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/raw_feed')
def raw_feed():
    return Response(stream_generator(use_ai=False),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/stats', methods=['GET'])
def get_stats():
    with lock:
        res = dict(latest_stats)
    return jsonify(res)

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        data = request.json or {}
        if "source_type" in data:
            config["source_type"] = data["source_type"]
        if "esp32_ip" in data:
            config["esp32_ip"] = data["esp32_ip"]
        if "com_port" in data:
            config["com_port"] = data["com_port"]
        if "mode" in data:
            detector.mode = data["mode"]
        if "motion_threshold" in data:
            detector.motion_threshold = int(data["motion_threshold"])
        if "min_contour_area" in data:
            detector.min_contour_area = int(data["min_contour_area"])
        if "auto_capture_motion" in data:
            config["auto_capture_motion"] = bool(data["auto_capture_motion"])
        return jsonify({"success": True, "config": config, "mode": detector.mode})

    return jsonify({"config": config, "mode": detector.mode})

@app.route('/api/flash', methods=['POST'])
def trigger_flash():
    data = request.json or {}
    state = data.get("state", not config["flash_state"])
    brightness = data.get("brightness", config["flash_brightness"])
    config["flash_state"] = state
    config["flash_brightness"] = brightness

    if config["source_type"] == "usb_serial":
        if state:
            send_serial_cmd(f"LB{brightness}")
        else:
            send_serial_cmd("L0")
    else:
        try:
            host = get_esp32_host()
            url = f"http://{host}/led?state={1 if state else 0}&brightness={brightness}"
            requests.get(url, timeout=1.5)
        except Exception:
            pass

    return jsonify({"success": True, "state": state, "brightness": brightness})

@app.route('/api/capture', methods=['POST'])
def manual_capture():
    with lock:
        frame = latest_processed_frame
    if frame is not None:
        filename = f"capture_{int(time.time())}.jpg"
        filepath = os.path.join(CAPTURES_DIR, filename)
        cv2.imwrite(filepath, frame)
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
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

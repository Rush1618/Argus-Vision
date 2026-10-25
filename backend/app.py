import cv2
import time
import threading
import os
import requests
import numpy as np
import serial
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from detector import VisionDetector

app = Flask(__name__, static_folder="captures")
CORS(app)

CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

# Configuration & State
config = {
    "source_type": "webcam",   # Default to webcam so hands & camera stream work immediately!
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

def get_serial_connection():
    global ser_instance
    with ser_lock:
        if ser_instance is None or not ser_instance.is_open:
            try:
                ser_instance = serial.Serial(config["com_port"], config["baud_rate"], timeout=0.05)
                ser_instance.dtr = False
                ser_instance.rts = False
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

def get_esp32_stream_url():
    ip = config["esp32_ip"].strip().replace("http://", "").replace("/", "")
    return f"http://{ip}:81/stream"

def generate_simulated_frame(message="SEARCHING FOR CAMERA..."):
    w, h = 640, 480
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(0, w, 40):
        cv2.line(frame, (x, 0), (x, h), (30, 20, 10), 1)
    for y in range(0, h, 40):
        cv2.line(frame, (0, y), (w, y), (30, 20, 10), 1)

    t = time.time()
    cx, cy = w // 2, h // 2
    radius = 120
    cv2.circle(frame, (cx, cy), radius, (0, 120, 255), 1)
    cv2.circle(frame, (cx, cy), radius // 2, (0, 80, 180), 1)
    angle = (t * 2) % (2 * np.pi)
    end_x = int(cx + radius * np.cos(angle))
    end_y = int(cy + radius * np.sin(angle))
    cv2.line(frame, (cx, cy), (end_x, end_y), (0, 255, 200), 2)

    cv2.putText(frame, message, (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2)
    cv2.putText(frame, f"Active Source: {config['source_type'].upper()}", (40, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1)
    return frame

def video_capture_worker():
    global latest_raw_frame, latest_processed_frame, latest_stats, last_frame_time
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

            elif curr_source == "webcam":
                if cap is None or last_source != "webcam":
                    if cap: cap.release()
                    cap = cv2.VideoCapture(config["webcam_index"], cv2.CAP_DSHOW)
                    last_source = "webcam"
                
                success, f = cap.read()
                if success and f is not None:
                    frame = f
                    last_frame_time = time.time()
                else:
                    # Retry with default backend if DSHOW failed
                    if cap: cap.release()
                    cap = cv2.VideoCapture(config["webcam_index"])
                    success, f = cap.read()
                    if success and f is not None:
                        frame = f
                        last_frame_time = time.time()

            # If selected hardware source (ESP32 / COM port) has no connection, fallback to active camera
            if frame is None and (time.time() - last_frame_time > 3.0):
                if cap is None or last_source != "webcam":
                    if cap: cap.release()
                    cap = cv2.VideoCapture(config["webcam_index"], cv2.CAP_DSHOW)
                    last_source = "webcam"
                if cap and cap.isOpened():
                    s, f = cap.read()
                    if s and f is not None:
                        frame = f
                        last_frame_time = time.time()

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
            is_stale = (time.time() - last_frame_time > 2.0)
            if jpeg_bytes is None or is_stale:
                sim_frame = generate_simulated_frame()
                _, buffer = cv2.imencode('.jpg', sim_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
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
            ip = config["esp32_ip"].strip().replace("http://", "").replace("/", "")
            url = f"http://{ip}/led?state={1 if state else 0}&brightness={brightness}"
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
    for f in sorted(os.listdir(CAPTURES_DIR), reverse=True):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            filepath = os.path.join(CAPTURES_DIR, f)
            files.append({
                "filename": f,
                "url": f"/captures/{f}",
                "size_kb": round(os.path.getsize(filepath) / 1024, 1),
                "timestamp": os.path.getmtime(filepath)
            })
    return jsonify(files)

@app.route('/captures/<path:filename>')
def serve_capture(filename):
    return send_from_directory(CAPTURES_DIR, filename)

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

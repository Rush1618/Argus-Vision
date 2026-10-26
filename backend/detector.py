import cv2
import numpy as np
import time
import os
import math
import json
import threading
from collections import deque

class VisionDetector:
    def __init__(self):
        # Neural Model instances
        self.yolo_model = None
        self.face_detector = None
        self.gesture_recognizer = None
        
        # Base paths
        self.backend_dir = os.path.dirname(os.path.abspath(__file__))
        self.models_dir = os.path.join(self.backend_dir, "models")
        os.makedirs(self.models_dir, exist_ok=True)
        self.custom_gestures_file = os.path.join(self.models_dir, "custom_gestures.json")
        self.lock = threading.Lock()
        
        # State variables
        self.prev_frame = None
        self.mode = "gesture" # Options: "gesture", "objects", "face", "motion", "edges", "night_vision", "raw"
        self.confidence_threshold = 0.40
        self.motion_threshold = 25
        self.min_contour_area = 800
        
        # Performance & Stats
        self.fps = 0.0
        self.last_time = time.time()
        self.frame_count = 0
        self.detected_count = 0
        self.motion_detected = False
        self.motion_level = 0.0
        self.last_gesture = "None"
        self.last_gesture_conf = 0.0

        # Finger Movement Geometric Trail Buffers (Tip Landmark indices: 4=Thumb, 8=Index, 12=Middle, 16=Ring, 20=Pinky)
        self.finger_trails = {
            4: deque(maxlen=14),   # Thumb
            8: deque(maxlen=22),   # Index (primary drawing trail)
            12: deque(maxlen=14),  # Middle
            16: deque(maxlen=12),  # Ring
            20: deque(maxlen=12),  # Pinky
        }
        self.last_hand_seen_time = 0

        # YouTube-Style Phrase & Caption Assembler
        self.caption_words = []
        self.current_sentence = ""
        self.last_stable_word = ""
        self.stable_word_start = 0
        self.last_committed_word = ""
        self.sentence_history = []
        self.latest_landmarks_vector = None

        # Load Custom Trained Gestures
        self.custom_gestures = self._load_custom_gestures()

        # Pre-warm models asynchronously for zero switching lag
        self.models_ready = {
            "yolo": False,
            "face": False,
            "gesture": False
        }
        threading.Thread(target=self._prewarm_all_models, daemon=True).start()

    # -------------------------------------------------------------
    # Custom Gesture Storage
    # -------------------------------------------------------------
    def _load_custom_gestures(self):
        if os.path.exists(self.custom_gestures_file):
            try:
                with open(self.custom_gestures_file, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_custom_gesture(self, phrase, vector):
        """Saves a normalized 63-element landmark vector for a custom phrase."""
        if not phrase or not vector or len(vector) != 63:
            return False
        clean_phrase = phrase.strip().upper()
        with self.lock:
            self.custom_gestures[clean_phrase] = vector
            try:
                with open(self.custom_gestures_file, "w") as f:
                    json.dump(self.custom_gestures, f, indent=2)
                print(f"[VisionDetector] Trained custom gesture: '{clean_phrase}'")
                return True
            except Exception as e:
                print(f"[VisionDetector] Error saving custom gesture: {e}")
                return False

    def clear_captions(self):
        with self.lock:
            self.caption_words.clear()
            self.current_sentence = ""
            self.last_committed_word = ""

    def reset_motion_history(self):
        with self.lock:
            self.prev_frame = None
            self.motion_detected = False
            self.motion_level = 0.0

    # -------------------------------------------------------------
    # Asynchronous Model Pre-Warming (Zero Switching Lag)
    # -------------------------------------------------------------
    def _prewarm_all_models(self):
        print("[VisionDetector] Starting background model pre-warming for zero-lag switching...")
        
        # 1. Warm Gesture Recognizer
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            model_path = os.path.join(self.models_dir, "gesture_recognizer.task")
            if os.path.exists(model_path):
                base_options = python.BaseOptions(model_asset_path=model_path)
                options = vision.GestureRecognizerOptions(
                    base_options=base_options,
                    running_mode=vision.RunningMode.IMAGE,
                    num_hands=2,
                    min_hand_detection_confidence=0.45,
                    min_hand_presence_confidence=0.45,
                    min_tracking_confidence=0.45
                )
                self.gesture_recognizer = vision.GestureRecognizer.create_from_options(options)
                dummy = np.zeros((240, 320, 3), dtype=np.uint8)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=dummy)
                self.gesture_recognizer.recognize(mp_image)
                self.models_ready["gesture"] = True
                print("[VisionDetector] Gesture Recognizer pre-warmed and ready.")
        except Exception as e:
            print(f"[VisionDetector] Gesture pre-warm note: {e}")

        # 2. Warm Face Detector (YuNet)
        try:
            yunet_path = os.path.join(self.models_dir, "face_detection_yunet_2023mar.onnx")
            if os.path.exists(yunet_path):
                self.face_detector = cv2.FaceDetectorYN.create(
                    yunet_path, "", (320, 320),
                    score_threshold=0.55,
                    nms_threshold=0.3,
                    top_k=8
                )
                dummy = np.zeros((320, 320, 3), dtype=np.uint8)
                self.face_detector.detect(dummy)
                self.face_input_size = (320, 320)
                self.models_ready["face"] = True
                print("[VisionDetector] YuNet Face Detector pre-warmed and ready.")
        except Exception as e:
            print(f"[VisionDetector] Face pre-warm note: {e}")

        # 3. Warm YOLOv8
        try:
            from ultralytics import YOLO
            candidates = [
                os.path.join(self.backend_dir, "yolov8n.pt"),
                os.path.join(self.backend_dir, "..", "yolov8n.pt"),
                "yolov8n.pt"
            ]
            model_path = next((p for p in candidates if os.path.exists(p)), "yolov8n.pt")
            self.yolo_model = YOLO(model_path)
            self.models_ready["yolo"] = True
            print("[VisionDetector] YOLOv8 loaded and ready.")
        except Exception as e:
            print(f"[VisionDetector] YOLO pre-warm note: {e}")

    # -------------------------------------------------------------
    # Main Process Frame Dispatcher
    # -------------------------------------------------------------
    def process_frame(self, frame):
        if frame is None:
            return None, {}

        self.frame_count += 1
        current_time = time.time()
        dt = current_time - self.last_time
        if dt > 0.5:
            self.fps = round(self.frame_count / dt, 1)
            self.frame_count = 0
            self.last_time = current_time

        h, w = frame.shape[:2]
        annotated = frame.copy()

        # Handle sentence break if no hand seen for > 3.0s
        if self.mode == "gesture" and self.caption_words and (current_time - self.last_hand_seen_time > 3.0):
            sentence = " ".join(self.caption_words).strip()
            if sentence and (not self.sentence_history or self.sentence_history[-1] != sentence):
                self.sentence_history.append(sentence)
                if len(self.sentence_history) > 10:
                    self.sentence_history.pop(0)
            self.caption_words.clear()
            self.last_committed_word = ""

        stats = {
            "mode": self.mode,
            "fps": self.fps,
            "resolution": f"{w}x{h}",
            "detections": 0,
            "motion_level": 0.0,
            "motion_detected": False,
            "gesture": self.last_gesture,
            "current_sentence": " ".join(self.caption_words) if self.caption_words else "",
            "last_word": self.last_committed_word,
            "sentence_history": list(self.sentence_history),
            "custom_gestures_count": len(self.custom_gestures)
        }

        # Clear finger trails if away from gesture mode or no hand for 1.5s
        if self.mode != "gesture" or (current_time - self.last_hand_seen_time > 1.5):
            for q in self.finger_trails.values():
                if len(q) > 0:
                    q.popleft()

        if self.mode == "raw":
            self._draw_hud(annotated, "Raw Sensor Feed", (180, 240, 200))
            return annotated, stats

        elif self.mode == "gesture":
            return self._process_gesture(frame, annotated, stats, w, h)

        elif self.mode == "objects":
            return self._process_objects(frame, annotated, stats, w, h)

        elif self.mode == "face":
            return self._process_face(frame, annotated, stats, w, h)

        elif self.mode == "motion":
            return self._process_motion(frame, annotated, stats, w, h)

        elif self.mode == "edges":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 70, 180)
            annotated = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
            annotated[:, :, 0] = np.where(edges > 0, 240, 0)
            annotated[:, :, 1] = np.where(edges > 0, 160, 0)
            annotated[:, :, 2] = np.where(edges > 0, 40, 0)
            self._draw_hud(annotated, "Canny Matrix Edge Filter", (240, 160, 40))
            return annotated, stats

        elif self.mode == "night_vision":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            annotated = np.zeros_like(frame)
            annotated[:, :, 1] = enhanced
            annotated[:, :, 0] = np.clip(enhanced * 0.35, 0, 255).astype(np.uint8)
            self._draw_hud(annotated, "Night Vision (CLAHE Boost)", (0, 255, 120))
            return annotated, stats

        return annotated, stats

    # -------------------------------------------------------------
    # Sign Language, Finger Trails & YouTube CC Caption Pipeline
    # -------------------------------------------------------------
    def _process_gesture(self, frame, annotated, stats, w, h):
        if self.gesture_recognizer is not None:
            try:
                import mediapipe as mp
                # 320x240 inference for ultra-smooth 60+ FPS performance
                small = cv2.resize(frame, (320, 240))
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                results = self.gesture_recognizer.recognize(mp_image)

                hand_count = len(results.hand_landmarks) if results.hand_landmarks else 0
                stats["detections"] = hand_count

                active_sign_tokens = []

                if hand_count > 0:
                    self.last_hand_seen_time = time.time()

                    for hand_idx, landmarks in enumerate(results.hand_landmarks):
                        pts = []
                        raw_vec = []
                        for lm in landmarks:
                            px, py = int(lm.x * w), int(lm.y * h)
                            pts.append((px, py))
                            raw_vec.extend([lm.x, lm.y, lm.z])

                        # Store latest normalized vector for user training
                        norm_vec = self._normalize_landmarks(pts)
                        self.latest_landmarks_vector = norm_vec

                        # 1. Update Finger Trails for Tips (4=Thumb, 8=Index, 12=Middle, 16=Ring, 20=Pinky)
                        for tip_idx in (4, 8, 12, 16, 20):
                            if tip_idx < len(pts):
                                self.finger_trails[tip_idx].append(pts[tip_idx])

                        # 2. Draw Glowing Finger Movement Trails (laser ribbons)
                        self._draw_finger_motion_trails(annotated)

                        # 3. Draw Dynamic Hand Geometric Constellation & Skeleton
                        self._draw_hand_constellation(annotated, pts)

                        # 4. Finger Distance & Geometry Measurements (Pinch, Span)
                        pinch_dist = math.hypot(pts[4][0] - pts[8][0], pts[4][1] - pts[8][1])
                        palm_scale = max(25.0, math.hypot(pts[0][0] - pts[9][0], pts[0][1] - pts[9][1]))
                        is_pinching = (pinch_dist / palm_scale) < 0.32

                        if pinch_dist < palm_scale * 0.8:
                            color = (0, 255, 120) if is_pinching else (0, 200, 255)
                            cv2.line(annotated, pts[4], pts[8], color, 2, cv2.LINE_AA)
                            mid_x, mid_y = (pts[4][0] + pts[8][0]) // 2, (pts[4][1] + pts[8][1]) // 2
                            if is_pinching:
                                cv2.putText(annotated, "PINCH", (mid_x + 8, mid_y),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 120), 1, cv2.LINE_AA)

                        # 5. Hand Enclosure Box
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        min_x, max_x = max(0, min(xs) - 18), min(w - 1, max(xs) + 18)
                        min_y, max_y = max(0, min(ys) - 18), min(h - 1, max(ys) + 18)
                        cv2.rectangle(annotated, (min_x, min_y), (max_x, max_y), (0, 220, 180), 1)

                        # 6. Recognize Sign Language & Gestures
                        gesture_token = None
                        gesture_name = "Sign"
                        gesture_conf = 0.0

                        # A. Check Custom Trained Gestures First
                        custom_match, custom_sim = self._match_custom_gesture(norm_vec)
                        if custom_match:
                            gesture_name = custom_match
                            gesture_token = custom_match
                            gesture_conf = custom_sim
                        else:
                            # B. MediaPipe Standard Recognizer
                            if results.gestures and hand_idx < len(results.gestures) and len(results.gestures[hand_idx]) > 0:
                                top_gesture = results.gestures[hand_idx][0]
                                g_cat = top_gesture.category_name
                                g_score = top_gesture.score

                                friendly_map = {
                                    "Thumb_Up": ("YES", "Thumbs Up (Yes / Affirmative)"),
                                    "Thumb_Down": ("NO", "Thumbs Down (No / Negative)"),
                                    "Victory": ("PEACE", "Peace / Victory (V)"),
                                    "Pointing_Up": ("ONE", "Pointing (One / You)"),
                                    "Open_Palm": ("HELLO", "Open Palm (Hello / Stop)"),
                                    "Closed_Fist": ("FIST", "Fist (Power / Solid)"),
                                    "ILoveYou": ("I LOVE YOU", "I Love You (ASL ILY)")
                                }
                                if g_cat in friendly_map:
                                    gesture_token, gesture_name = friendly_map[g_cat]
                                    gesture_conf = g_score

                            # C. Geometric ASL Finger Extensions
                            asl_token, asl_name = self._classify_finger_geometry(pts, palm_scale)
                            if asl_name:
                                gesture_token = asl_token
                                gesture_name = asl_name
                                gesture_conf = 0.94

                        if gesture_token:
                            active_sign_tokens.append(gesture_token)

                        # Display tag above hand
                        badge_txt = f"{gesture_name}"
                        if gesture_conf > 0:
                            badge_txt += f" ({int(gesture_conf * 100)}%)"

                        cv2.rectangle(annotated, (min_x, max(0, min_y - 24)), (min_x + len(badge_txt) * 8 + 12, min_y), (14, 20, 30), -1)
                        cv2.rectangle(annotated, (min_x, max(0, min_y - 24)), (min_x + len(badge_txt) * 8 + 12, min_y), (0, 220, 180), 1)
                        cv2.putText(annotated, badge_txt, (min_x + 6, min_y - 7),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (240, 246, 255), 1, cv2.LINE_AA)

                    # 7. Update Temporal Caption Phrase Assembler
                    self._update_caption_sequencer(active_sign_tokens)

                    active_str = " + ".join(active_sign_tokens) if active_sign_tokens else "Hand tracking"
                    stats["gesture"] = active_str
                    self.last_gesture = active_str
                    self._draw_hud(annotated, f"Sign: {active_str}", (0, 220, 180))
                else:
                    self._draw_hud(annotated, "Sign Language Captions: Move Hand in View", (140, 170, 190))

                # 8. Render YouTube-Style Live Closed Captions (CC) Overlay on Video
                active_caption = " ".join(self.caption_words).strip()
                if not active_caption and self.last_committed_word:
                    active_caption = self.last_committed_word
                elif not active_caption and active_sign_tokens:
                    active_caption = active_sign_tokens[0]

                if active_caption:
                    self._draw_youtube_captions(annotated, f"[CC] {active_caption}")

                stats["current_sentence"] = active_caption
                stats["last_word"] = self.last_committed_word
                return annotated, stats
            except Exception as e:
                print(f"[VisionDetector] Gesture execution error: {e}")

        return self._fallback_target_tracker(frame, annotated, stats, w, h, label_prefix="Hand Region")

    # -------------------------------------------------------------
    # YouTube-Style Closed Caption (CC) Subtitle Overlay
    # -------------------------------------------------------------
    def _draw_youtube_captions(self, img, text):
        if not text:
            return
        h, w = img.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.58
        thickness = 2
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
        
        pad_x, pad_y = 16, 9
        box_w = tw + pad_x * 2
        box_h = th + pad_y * 2
        box_x = max(16, (w - box_w) // 2)
        box_y = h - 60

        # Semi-transparent YouTube CC black background box
        overlay = img.copy()
        cv2.rectangle(overlay, (box_x, box_y), (box_x + box_w, box_y + box_h), (6, 8, 12), -1)
        cv2.addWeighted(overlay, 0.88, img, 0.12, 0, img)

        # YouTube subtitle white/yellow text with clean drop shadow
        cv2.putText(img, text, (box_x + pad_x + 1, box_y + box_h - pad_y + 1),
                    font, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
        cv2.putText(img, text, (box_x + pad_x, box_y + box_h - pad_y),
                    font, scale, (252, 254, 255), thickness, cv2.LINE_AA)

    # -------------------------------------------------------------
    # Caption Sequencer (Commits Words after 0.6s Stability)
    # -------------------------------------------------------------
    def _update_caption_sequencer(self, active_tokens):
        if not active_tokens:
            return
        
        token = active_tokens[0]
        now = time.time()

        with self.lock:
            if token == self.last_stable_word:
                # If held for >= 0.6 seconds, commit to active sentence
                if (now - self.stable_word_start) >= 0.6:
                    if not self.caption_words or self.caption_words[-1] != token:
                        self.caption_words.append(token)
                        self.last_committed_word = token
                        if len(self.caption_words) > 8:
                            self.caption_words.pop(0)
                    self.stable_word_start = now + 0.4
            else:
                self.last_stable_word = token
                self.stable_word_start = now

    # -------------------------------------------------------------
    # Custom Gesture Landmark Normalization & Cosine Matching
    # -------------------------------------------------------------
    def _normalize_landmarks(self, pts):
        """Creates a scale and translation invariant 63-element landmark vector."""
        if len(pts) < 21:
            return None
        # Translate relative to wrist (index 0)
        wx, wy = pts[0][0], pts[0][1]
        palm_dist = max(15.0, math.hypot(pts[9][0] - wx, pts[9][1] - wy))
        
        vec = []
        for x, y in pts:
            vec.extend([(x - wx) / palm_dist, (y - wy) / palm_dist, 0.0])
        
        arr = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 1e-6:
            arr = arr / norm
        return arr.tolist()

    def _match_custom_gesture(self, norm_vec):
        """Matches normalized hand vector against user-trained gestures."""
        if not norm_vec:
            return None, 0.0

        with self.lock:
            if not self.custom_gestures:
                return None, 0.0
            gestures_snapshot = list(self.custom_gestures.items())

        v1 = np.array(norm_vec, dtype=np.float32)
        best_name = None
        best_sim = 0.0

        for phrase, template in gestures_snapshot:
            v2 = np.array(template, dtype=np.float32)
            sim = float(np.dot(v1, v2))
            if sim > best_sim:
                best_sim = sim
                best_name = phrase

        if best_sim >= 0.88:
            return best_name, best_sim
        return None, 0.0

    # -------------------------------------------------------------
    # Finger Motion Trails (Laser Movement Ribbon)
    # -------------------------------------------------------------
    def _draw_finger_motion_trails(self, img):
        trail = self.finger_trails[8]
        n = len(trail)
        if n > 1:
            for i in range(1, n):
                p1 = trail[i - 1]
                p2 = trail[i]
                alpha = float(i) / n
                thickness = max(1, int(3 * alpha))
                color = (
                    int(255 * alpha),
                    int(220 * alpha),
                    int(30 * (1.0 - alpha))
                )
                cv2.line(img, p1, p2, color, thickness, cv2.LINE_AA)
                cv2.circle(img, p2, thickness, (0, 255, 220), -1, cv2.LINE_AA)

        thumb_trail = self.finger_trails[4]
        tn = len(thumb_trail)
        if tn > 1:
            for i in range(1, tn):
                p1 = thumb_trail[i - 1]
                p2 = thumb_trail[i]
                alpha = float(i) / tn
                color = (int(60 * alpha), int(220 * alpha), int(255 * alpha))
                cv2.line(img, p1, p2, color, 1, cv2.LINE_AA)

    # -------------------------------------------------------------
    # Hand Constellation Geometry
    # -------------------------------------------------------------
    def _draw_hand_constellation(self, img, pts):
        bones = [
            (0,1),(1,2),(2,3),(3,4),       # Thumb
            (0,5),(5,6),(6,7),(7,8),       # Index
            (5,9),(9,10),(10,11),(11,12),  # Middle
            (9,13),(13,14),(14,15),(15,16),# Ring
            (13,17),(17,18),(18,19),(19,20), # Pinky
            (0,17)                         # Palm base
        ]

        for u, v in bones:
            if u < len(pts) and v < len(pts):
                cv2.line(img, pts[u], pts[v], (0, 180, 150), 2, cv2.LINE_AA)

        tips = [4, 8, 12, 16, 20]
        for i in range(len(tips) - 1):
            t1, t2 = tips[i], tips[i+1]
            if t1 < len(pts) and t2 < len(pts):
                cv2.line(img, pts[t1], pts[t2], (50, 90, 110), 1, cv2.LINE_AA)

        for idx, pt in enumerate(pts):
            if idx in tips:
                cv2.circle(img, pt, 5, (0, 240, 255), -1, cv2.LINE_AA)
                cv2.circle(img, pt, 8, (0, 200, 160), 1, cv2.LINE_AA)
            else:
                cv2.circle(img, pt, 3, (0, 220, 160), -1, cv2.LINE_AA)

    # -------------------------------------------------------------
    # ASL & Sign Language Finger Geometry Classifier
    # -------------------------------------------------------------
    def _classify_finger_geometry(self, pts, palm_scale):
        if len(pts) < 21:
            return None, None

        index_up = pts[8][1] < pts[6][1]
        middle_up = pts[12][1] < pts[10][1]
        ring_up = pts[16][1] < pts[14][1]
        pinky_up = pts[20][1] < pts[18][1]
        thumb_out = abs(pts[4][0] - pts[2][0]) > (palm_scale * 0.38)

        # OK Sign (F)
        thumb_index_dist = math.hypot(pts[4][0] - pts[8][0], pts[4][1] - pts[8][1])
        if (thumb_index_dist / palm_scale) < 0.35 and middle_up and ring_up and pinky_up:
            return "OK", "Sign 'OK' / 'F' (Agreement)"

        # Sign 'L'
        if index_up and thumb_out and not middle_up and not ring_up and not pinky_up:
            return "L", "Sign 'L' (Letter L)"

        # Sign 'W' / 3
        if index_up and middle_up and ring_up and not pinky_up:
            return "W", "Sign 'W' (Letter W / 3)"

        # Sign 'Y' / Call Me
        if thumb_out and not index_up and not middle_up and not ring_up and pinky_up:
            return "CALL ME", "Sign 'Y' (Call Me / Letter Y)"

        # Sign 'One'
        if index_up and not middle_up and not ring_up and not pinky_up and not thumb_out:
            return "ONE", "Sign 'One' (Direction / 1)"

        return None, None

    # -------------------------------------------------------------
    # Object Detection Pipeline (YOLOv8)
    # -------------------------------------------------------------
    def _process_objects(self, frame, annotated, stats, w, h):
        if self.yolo_model is not None:
            try:
                results = self.yolo_model(frame, verbose=False, conf=self.confidence_threshold, imgsz=320)[0]
                detected_objects = 0
                for box in results.boxes:
                    detected_objects += 1
                    xyxy = box.xyxy[0].cpu().numpy().astype(int)
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())
                    name = results.names.get(cls_id, f"obj_{cls_id}").title()

                    x1, y1, x2, y2 = xyxy
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 180), 2)
                    
                    clen = max(8, int(min(x2 - x1, y2 - y1) * 0.18))
                    cv2.line(annotated, (x1, y1), (x1 + clen, y1), (0, 255, 140), 2)
                    cv2.line(annotated, (x1, y1), (x1, y1 + clen), (0, 255, 140), 2)
                    cv2.line(annotated, (x2, y1), (x2 - clen, y1), (0, 255, 140), 2)
                    cv2.line(annotated, (x2, y1), (x2, y1 + clen), (0, 255, 140), 2)

                    label = f"{name} {int(conf * 100)}%"
                    cv2.rectangle(annotated, (x1, max(0, y1 - 22)), (x1 + len(label) * 8 + 10, y1), (14, 22, 34), -1)
                    cv2.rectangle(annotated, (x1, max(0, y1 - 22)), (x1 + len(label) * 8 + 10, y1), (0, 220, 180), 1)
                    cv2.putText(annotated, label, (x1 + 4, y1 - 6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (240, 246, 255), 1, cv2.LINE_AA)

                stats["detections"] = detected_objects
                self.detected_count = detected_objects
                self._draw_hud(annotated, f"Neural Objects: {detected_objects} detected", (0, 220, 180))
                return annotated, stats
            except Exception as e:
                print(f"[VisionDetector] YOLO execution note: {e}")

        return self._fallback_target_tracker(frame, annotated, stats, w, h, label_prefix="Target Entity")

    # -------------------------------------------------------------
    # Face & Landmark Detection Pipeline (YuNet)
    # -------------------------------------------------------------
    def _process_face(self, frame, annotated, stats, w, h):
        if self.face_detector is not None:
            try:
                if getattr(self, 'face_input_size', None) != (w, h):
                    self.face_detector.setInputSize((w, h))
                    self.face_input_size = (w, h)

                _, faces = self.face_detector.detect(frame)
                face_count = 0
                if faces is not None:
                    face_count = len(faces)
                    for face in faces:
                        fx, fy, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
                        conf = face[-1]

                        cv2.rectangle(annotated, (fx, fy), (fx + fw, fy + fh), (0, 255, 140), 2)
                        
                        clen = max(8, int(min(fw, fh) * 0.2))
                        cv2.line(annotated, (fx, fy), (fx + clen, fy), (0, 220, 180), 2)
                        cv2.line(annotated, (fx, fy), (fx, fy + clen), (0, 220, 180), 2)
                        cv2.line(annotated, (fx + fw, fy), (fx + fw - clen, fy), (0, 220, 180), 2)
                        cv2.line(annotated, (fx + fw, fy), (fx + fw, fy + clen), (0, 220, 180), 2)

                        landmarks = [
                            (int(face[4]), int(face[5])),   # Right eye
                            (int(face[6]), int(face[7])),   # Left eye
                            (int(face[8]), int(face[9])),   # Nose tip
                            (int(face[10]), int(face[11])), # Right mouth
                            (int(face[12]), int(face[13]))  # Left mouth
                        ]
                        for lx, ly in landmarks:
                            cv2.circle(annotated, (lx, ly), 3, (0, 220, 255), -1)

                        label = f"Face Target ({int(conf * 100)}%)"
                        cv2.rectangle(annotated, (fx, max(0, fy - 22)), (fx + len(label) * 8 + 8, fy), (14, 22, 34), -1)
                        cv2.rectangle(annotated, (fx, max(0, fy - 22)), (fx + len(label) * 8 + 8, fy), (0, 255, 140), 1)
                        cv2.putText(annotated, label, (fx + 4, fy - 6),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (240, 246, 255), 1, cv2.LINE_AA)

                stats["detections"] = face_count
                self._draw_hud(annotated, f"Face Tracker: {face_count} locked", (0, 255, 140))
                return annotated, stats
            except Exception as e:
                print(f"[VisionDetector] YuNet inference note: {e}")

        return self._fallback_target_tracker(frame, annotated, stats, w, h, label_prefix="Target Face")

    # -------------------------------------------------------------
    # Motion Detection Pipeline
    # -------------------------------------------------------------
    def _process_motion(self, frame, annotated, stats, w, h):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self.prev_frame is None:
            self.prev_frame = gray
            return annotated, stats

        frame_diff = cv2.absdiff(self.prev_frame, gray)
        thresh = cv2.threshold(frame_diff, self.motion_threshold, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)

        contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        motion_areas = 0
        total_motion_pixels = cv2.countNonZero(thresh)
        self.motion_level = round((total_motion_pixels / (w * h)) * 100, 1)

        for c in contours:
            if cv2.contourArea(c) < self.min_contour_area:
                continue
            motion_areas += 1
            (x, y, mw, mh) = cv2.boundingRect(c)
            cv2.rectangle(annotated, (x, y), (x + mw, y + mh), (40, 60, 230), 2)
            cv2.putText(annotated, "Movement Intrusion", (x, max(15, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (40, 60, 230), 1, cv2.LINE_AA)

        self.motion_detected = motion_areas > 0
        stats["motion_detected"] = self.motion_detected
        stats["motion_level"] = self.motion_level
        stats["detections"] = motion_areas

        self.prev_frame = gray
        hud_color = (40, 60, 230) if self.motion_detected else (0, 255, 140)
        status_text = f"Motion Sentry: {'Alert' if self.motion_detected else 'Secure'} ({self.motion_level}%)"
        self._draw_hud(annotated, status_text, hud_color)
        return annotated, stats

    # -------------------------------------------------------------
    # Adaptive Fallback Target Tracker
    # -------------------------------------------------------------
    def _fallback_target_tracker(self, frame, annotated, stats, w, h, label_prefix="Entity"):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (15, 15), 0)
        thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 19, 3)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        valid_targets = []
        for c in contours:
            area = cv2.contourArea(c)
            if 1500 < area < (w * h * 0.7):
                x, y, bw, bh = cv2.boundingRect(c)
                aspect = float(bw) / bh
                if 0.4 < aspect < 2.5:
                    valid_targets.append((x, y, bw, bh))

        valid_targets = sorted(valid_targets, key=lambda b: b[2] * b[3], reverse=True)[:3]
        stats["detections"] = len(valid_targets)

        for idx, (x, y, bw, bh) in enumerate(valid_targets):
            cv2.rectangle(annotated, (x, y), (x + bw, y + bh), (0, 255, 140), 2)
            label = f"{label_prefix} #{idx+1} [Acquired]"
            cv2.putText(annotated, label, (x, max(20, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 140), 1, cv2.LINE_AA)

        self._draw_hud(annotated, f"Target Tracker: {len(valid_targets)} locked", (0, 255, 140))
        return annotated, stats

    # -------------------------------------------------------------
    # Tactile Engineering HUD Overlay
    # -------------------------------------------------------------
    def _draw_hud(self, img, title, color):
        h, w = img.shape[:2]
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, 32), (14, 18, 26), -1)
        cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)

        cx, cy = w // 2, h // 2
        cv2.line(img, (cx - 12, cy), (cx + 12, cy), (120, 200, 220), 1)
        cv2.line(img, (cx, cy - 12), (cx, cy + 12), (120, 200, 220), 1)
        cv2.circle(img, (cx, cy), 18, (120, 200, 220), 1)

        cv2.putText(img, f"ESP32-CAM AI: {title}", (12, 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)
        
        fps_str = f"{self.fps} fps"
        cv2.putText(img, fps_str, (w - 78, 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (200, 220, 240), 1, cv2.LINE_AA)

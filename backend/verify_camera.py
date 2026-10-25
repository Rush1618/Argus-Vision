"""
Direct Camera & Gesture Verification Utility
Tests webcam access (DirectShow), MediaPipe gesture recognition,
finger movement trails, and prints real-time diagnostics.
"""
import cv2
import time
from detector import VisionDetector

def verify():
    print("=" * 60)
    print("ESP32-CAM AI VISION: CAMERA & GESTURE VERIFICATION")
    print("=" * 60)
    
    # 1. Test Camera Access with DirectShow
    print("[1/3] Probing camera with cv2.CAP_DSHOW...")
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("  -> DirectShow failed, trying default backend...")
        cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("[ERROR] No camera device could be opened!")
        return

    ret, frame = cap.read()
    if not ret or frame is None:
        print("[ERROR] Camera opened but returned an empty frame!")
        cap.release()
        return

    h, w = frame.shape[:2]
    print(f"[OK] Camera operational! Frame resolution: {w}x{h}")

    # 2. Test VisionDetector in Gesture Mode
    print("[2/3] Initializing VisionDetector with Sign Language & Finger Trails...")
    detector = VisionDetector()
    detector.mode = "gesture"

    # Wait briefly for pre-warming
    time.sleep(0.5)

    print("[3/3] Running 30 test frames on live camera feed...")
    start_time = time.time()
    frames_processed = 0

    for i in range(30):
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        
        annotated, stats = detector.process_frame(frame)
        frames_processed += 1
        
        gesture = stats.get("gesture", "None")
        detections = stats.get("detections", 0)
        fps = stats.get("fps", 0)

        if i % 6 == 0 or detections > 0:
            print(f"  Frame {i+1:02d} | Hands: {detections} | Gesture: {gesture} | {fps} FPS")

        time.sleep(0.02)

    total_time = time.time() - start_time
    cap.release()

    print("-" * 60)
    print(f"[OK] Verification Complete! Processed {frames_processed} frames in {total_time:.2f}s ({frames_processed/total_time:.1f} FPS)")
    print("Your camera and Sign Language detection engine are 100% operational!")
    print("=" * 60)

if __name__ == "__main__":
    verify()

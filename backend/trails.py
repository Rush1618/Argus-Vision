import cv2
import numpy as np
from collections import deque

class FingerTrailRenderer:
    def __init__(self):
        # Tip landmark indices: 4=Thumb, 8=Index, 12=Middle, 16=Ring, 20=Pinky
        self.trails = {
            4: deque(maxlen=14),   # Thumb
            8: deque(maxlen=24),   # Index (primary drawing trail)
            12: deque(maxlen=14),  # Middle
            16: deque(maxlen=12),  # Ring
            20: deque(maxlen=12),  # Pinky
        }
        self.colors = {
            4: (0, 200, 255),   # Amber/Gold
            8: (0, 255, 120),   # Neon Emerald
            12: (255, 120, 0),  # Electric Cyan/Blue
            16: (220, 60, 255), # Magenta/Violet
            20: (60, 220, 255), # Yellow
        }

    def update(self, pts):
        """Appends new fingertip positions to trail deques."""
        for tip_idx in (4, 8, 12, 16, 20):
            if tip_idx < len(pts):
                self.trails[tip_idx].append(pts[tip_idx])

    def decay(self):
        """Fades out trails when no hands are in view."""
        for q in self.trails.values():
            if len(q) > 0:
                q.popleft()

    def draw(self, img):
        """Renders glowing laser trails with fading thickness and alpha blend."""
        overlay = img.copy()
        for tip_idx, pts_queue in self.trails.items():
            if len(pts_queue) < 2:
                continue
            color = self.colors.get(tip_idx, (0, 255, 140))
            pts_list = list(pts_queue)
            for i in range(1, len(pts_list)):
                alpha = float(i) / len(pts_list)
                thickness = max(1, int(alpha * 5.0))
                p1, p2 = pts_list[i - 1], pts_list[i]
                cv2.line(overlay, p1, p2, color, thickness + 2, cv2.LINE_AA)
                cv2.line(img, p1, p2, (255, 255, 255), max(1, thickness - 1), cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.45, img, 0.55, 0, img)

    def draw_constellation(self, img, pts):
        """Draws sacred geometry connections between fingertips and palm center."""
        if len(pts) < 21:
            return
        palm_center = pts[9] # Base of middle finger
        tips = [pts[4], pts[8], pts[12], pts[16], pts[20]]

        # Finger-to-finger polygon
        for i in range(len(tips) - 1):
            cv2.line(img, tips[i], tips[i + 1], (0, 220, 180), 1, cv2.LINE_AA)

        # Star lines to palm center
        for t in tips:
            cv2.line(img, t, palm_center, (0, 140, 255), 1, cv2.LINE_AA)
            cv2.circle(img, t, 4, (0, 255, 140), -1, cv2.LINE_AA)

        cv2.circle(img, palm_center, 6, (0, 200, 255), 1, cv2.LINE_AA)

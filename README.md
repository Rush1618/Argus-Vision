# ⚡ ESP32-CAM AI Vision System & Cyber Console

An enterprise-grade, full-stack AI Computer Vision platform for the **ESP32-CAM** (AI-Thinker module) featuring real-time neural object detection, face and movement tracking, hardware flashlight control, and a modern, high-tech React HUD dashboard.

---

## 🌟 Key Features

1. **High-Performance ESP32-CAM Firmware (`.ino`)**:
   - High-throughput MJPEG live video streaming (`/stream`) with double buffering on PSRAM.
   - High-resolution single-frame snapshot endpoint (`/capture`).
   - Hardware Flash LED PWM brightness control on GPIO 4 (`/led?state=1&brightness=255`).
   - Device status telemetry JSON (`/status`) with RSSI, IP, heap, and sensor parameters.
   - Automatic fallback to SoftAP Mode (`ESP32-CAM-Vision` / `password123`) if Wi-Fi cannot connect.

2. **Advanced AI & Computer Vision Backend (Python + OpenCV + YOLOv8)**:
   - **Neural Object Detection (YOLOv8)**: Detects 80 everyday objects (people, vehicles, pets, phones, laptops, cups, etc.) with bounding boxes and confidence levels.
   - **Face & Eye Tracker**: Precision target crosshairs and eye tracking.
   - **Motion Sentry Alarm**: Differential frame analysis with intrusion bounding boxes and configurable sensitivity.
   - **Night Vision (CLAHE)**: Adaptive contrast histogram equalization for low-light environments.
   - **Canny Matrix**: Cyberpunk neon edge detection visualizer.
   - **Intrusion Auto-Capture**: Automatically snapshots intruders and saves them to local disk.

3. **Modern Cyber React Dashboard**:
   - Tactical HUD overlay with target crosshairs, live FPS telemetry, and scanlines.
   - Flashlight slider & toggle with instant hardware sync.
   - Snapshot gallery with full-resolution lightbox viewer and one-click downloads.
   - Multi-source switcher: Stream from ESP32-CAM over Wi-Fi, local USB webcam, or synthetic radar simulator.

---

## 🔌 Hardware Wiring & Pinout (AI-Thinker ESP32-CAM)

To flash the ESP32-CAM using an **FTDI USB-to-Serial Programmer**:

| FTDI Pin | ESP32-CAM Pin | Description |
|---|---|---|
| **VCC (5V)** | **5V** | Power supply (Use minimum 5V / 2A for stable Wi-Fi!) |
| **GND** | **GND** | Ground |
| **TX** | **U0R (GPIO 3)** | Serial Receive |
| **RX** | **U0T (GPIO 1)** | Serial Transmit |
| **GND** | **GPIO 0** | **Connect GPIO 0 to GND ONLY while flashing** |

> ⚠️ **Important Flashing Note**:
> 1. Connect **GPIO 0 to GND** before plugging the FTDI module into USB.
> 2. Press the **RST** button on the back of the ESP32-CAM to enter Flash mode.
> 3. Click **Upload** in Arduino IDE.
> 4. Once uploaded (100%), **disconnect GPIO 0 from GND** and press **RST** once more to start normal boot!

---

## 🚀 Quickstart Guide

### 1. Flash the ESP32-CAM Firmware
1. Open `firmware/esp32_cam_streamer/esp32_cam_streamer.ino` in **Arduino IDE**.
2. Go to **Tools > Board > ESP32 Arduino > AI Thinker ESP32-CAM**.
3. Set **CPU Frequency: 240MHz**, **Flash Frequency: 80MHz**, **Partition Scheme: Huge APP (3MB No OTA)**.
4. Update your Wi-Fi credentials in the code:
   ```cpp
   const char* ssid = "YOUR_WIFI_NAME";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```
5. Upload the code and open the **Serial Monitor (115200 baud)** to view your camera's local IP address (e.g. `192.168.1.100`).

---

### 2. Run the AI Python Backend
In a terminal window:
```powershell
# Navigate to backend and run
python backend/app.py
```
* Backend API: `http://localhost:5000`
* Live AI Stream: `http://localhost:5000/video_feed`

---

### 3. Run the Modern Web Dashboard
In another terminal window:
```powershell
cd frontend
npm run dev
```
Open **`http://localhost:5173`** in your browser!

1. Type your ESP32-CAM's IP into the **Camera Stream Source** field and click **Connect**.
2. Switch between **Neural Objects**, **Face Tracker**, **Motion Sentry**, and **Night Vision**!
3. Control the on-board high-power Flash LED slider directly from your web browser.

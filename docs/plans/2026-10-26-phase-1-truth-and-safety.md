# Phase 1: System Truthfulness and Safety Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate silent desktop-screen fallback, enforce truthful connection and source telemetry, secure the Flask API and ESP32 endpoints against unauthorized access, and ensure hardware commands (flash/LED) report genuine execution status.

**Architecture:** Refactor the backend capture engine to track `selected_source`, `active_source`, and per-source connection health with clean resource disposal on transitions; replace automatic desktop capture with an explicit standby frame; bind Flask to `127.0.0.1` with schema-validated endpoints; secure ESP32-CAM firmware with an access-point password and token-authorized control endpoints; and update the React frontend to respect backend connection reality and configurable API base URLs.

**Tech Stack:** Python 3 (Flask, OpenCV, PySerial, Requests, unittest), C++ / Arduino (ESP-IDF / ESP32-CAM HTTP Server), React 19 + Vite.

---

### Task 1: Backend Connection State, Source Tracking & Standby Frame

**Files:**
- Modify: `backend/app.py:19-110, 111-300`
- Create: `backend/tests/test_source_and_connection.py`

**Step 1: Write the failing unit tests for source configuration and connection truth**

Create `backend/tests/test_source_and_connection.py`:
```python
import unittest
from unittest.mock import patch, MagicMock
import numpy as np

class TestSourceAndConnectionTruth(unittest.TestCase):
    def setUp(self):
        import backend.app as app_module
        self.app = app_module

    def test_default_source_is_standby_not_screen(self):
        # Default source must be 'standby' to protect user privacy
        self.assertEqual(self.app.config.get("source_type"), "standby")

    def test_standby_frame_generator(self):
        frame = self.app.generate_standby_frame("TEST STANDBY")
        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape, (480, 640, 3))

    def test_telemetry_separates_selected_and_active_source(self):
        # When source is esp32_wifi and no frames have arrived,
        # active_source must be None and connected must be False
        self.app.config["source_type"] = "esp32_wifi"
        self.app.active_source = None
        self.app.source_connected = False
        
        stats = self.app.get_current_telemetry()
        self.assertEqual(stats["selected_source"], "esp32_wifi")
        self.assertIsNone(stats["active_source"])
        self.assertFalse(stats["connected"])

if __name__ == '__main__':
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest backend/tests/test_source_and_connection.py -v`
Expected: FAIL (`AttributeError` or assertion failure because default source is currently `"screen"` and `get_current_telemetry` does not exist).

**Step 3: Implement minimal code in `backend/app.py`**

1. Change `config["source_type"]` default to `"standby"`.
2. Add global state tracking:
   ```python
   selected_source = "standby"
   active_source = None
   source_connected = False
   source_error = None
   ```
3. Implement `generate_standby_frame(status_text="STANDBY / NO CAMERA CONNECTED", sub_text="")`:
   Renders a high-contrast dark telemetry HUD standby graphic with watermark and source status.
4. Implement `get_current_telemetry()` returning:
   ```python
   {
       "selected_source": config["source_type"],
       "active_source": active_source,
       "connected": source_connected,
       "source_error": source_error,
       "last_frame_age": round(time.time() - last_frame_time, 2) if last_frame_time else None,
       **latest_stats
   }
   ```
5. Remove silent screen fallback in `video_capture_worker`:
   - Never capture the screen when `curr_source` is `usb_serial`, `esp32_wifi`, or `webcam`.
   - If no frame is received within timeout (1.5s), mark `source_connected = False`, `active_source = None`, `source_error = f"No signal from {curr_source}"`.
   - In standby mode or when disconnected, push `generate_standby_frame()` through the pipeline so streams show an explicit disconnected card rather than personal desktop screen contents.

**Step 4: Run tests to verify they pass**

Run: `python3 -m unittest backend/tests/test_source_and_connection.py -v`
Expected: PASS

**Step 5: Commit changes**

```bash
git add backend/app.py backend/tests/test_source_and_connection.py
git commit -m "fix(backend): enforce truthful source status and eliminate silent screen fallback"
```

---

### Task 2: Resource Lifecycle & Clean Source Transitions in Capture Worker

**Files:**
- Modify: `backend/app.py:58-80, 111-260`
- Create: `backend/tests/test_resource_cleanup.py`

**Step 1: Write the failing unit tests for resource cleanup**

Create `backend/tests/test_resource_cleanup.py`:
```python
import unittest
from unittest.mock import MagicMock, patch

class TestResourceCleanup(unittest.TestCase):
    def setUp(self):
        import backend.app as app_module
        self.app = app_module

    def test_cleanup_previous_source_releases_handles(self):
        mock_cap = MagicMock()
        mock_response = MagicMock()
        mock_serial = MagicMock()

        self.app.release_source_resources(mock_cap, mock_response, mock_serial)

        mock_cap.release.assert_called_once()
        mock_response.close.assert_called_once()
        mock_serial.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest backend/tests/test_resource_cleanup.py -v`
Expected: FAIL (`AttributeError: module 'backend.app' has no attribute 'release_source_resources'`).

**Step 3: Implement minimal resource release function and call it on source switch**

In `backend/app.py`:
1. Define `release_source_resources(cap, stream_response, ser)`:
   ```python
   def release_source_resources(cap=None, stream_response=None, ser=None):
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
   ```
2. In `video_capture_worker()`, detect when `curr_source != last_source`:
   - Call `release_source_resources(cap, stream_response, ser_instance)`.
   - Reset `serial_buf = b''`, `stream_bytes = b''`, `cap = None`, `stream_response = None`.
   - Call `detector.reset_motion_history()` so motion difference state does not carry over between unrelated sources (addresses finding F-08).

**Step 4: Run tests to verify they pass**

Run: `python3 -m unittest backend/tests/test_resource_cleanup.py -v`
Expected: PASS

**Step 5: Commit changes**

```bash
git add backend/app.py backend/tests/test_resource_cleanup.py
git commit -m "fix(backend): release hardware, serial, and HTTP stream handles on source transitions"
```

---

### Task 3: Secure Local Binding, Input Validation & Verified Hardware Flash Control

**Files:**
- Modify: `backend/app.py:10-15, 334-378, 462-464`
- Create: `backend/tests/test_api_security_and_validation.py`

**Step 1: Write the failing unit tests for API binding, validation, and flash feedback**

Create `backend/tests/test_api_security_and_validation.py`:
```python
import unittest
import json
from unittest.mock import patch

class TestApiSecurityAndValidation(unittest.TestCase):
    def setUp(self):
        import backend.app as app_module
        self.app = app_module.app
        self.client = self.app.test_client()

    def test_config_invalid_source_rejected(self):
        res = self.client.post('/api/config', json={"source_type": "invalid_source"})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get("success", False))

    def test_config_valid_source_accepted(self):
        res = self.client.post('/api/config', json={"source_type": "standby"})
        self.assertEqual(res.status_code, 200)

    def test_flash_fails_when_hardware_unreachable(self):
        # When ESP32 Wi-Fi is unreachable, /api/flash must return 502/503 failure, not fake success
        with patch('backend.app.requests.get', side_effect=Exception("Connection refused")):
            res = self.client.post('/api/flash', json={"state": True, "brightness": 200})
            self.assertEqual(res.status_code, 502)
            data = res.get_json()
            self.assertFalse(data.get("success", True))
            self.assertIn("error", data)

if __name__ == '__main__':
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest backend/tests/test_api_security_and_validation.py -v`
Expected: FAIL (invalid source accepted with 200, flash returns 200 despite connection failure).

**Step 3: Implement validation, local security, and verified flash execution**

In `backend/app.py`:
1. Bind default host to `127.0.0.1` (or read `ARGUS_HOST` env var, defaulting to `127.0.0.1`):
   ```python
   HOST = os.environ.get("ARGUS_HOST", "127.0.0.1")
   PORT = int(os.environ.get("ARGUS_PORT", 5000))
   ```
2. Validate `/api/config`:
   - Allowed sources: `{"standby", "screen", "webcam", "usb_serial", "esp32_wifi", "simulated"}`
   - Allowed modes: `{"face", "gesture", "object", "motion", "edge", "night", "raw"}`
   - Validate IP string format for `esp32_ip` to avoid SSRF to internal cloud metadata (reject `169.254.*` or non-IP hosts if unconfigured).
   - Constrain numeric parameters (`motion_threshold` between 1 and 255).
   - Return structured 400 Bad Request on invalid payloads.
3. Fix `/api/flash`:
   - If `usb_serial`: verify `ser_instance is not None and ser_instance.is_open`. If not open, return `{"success": False, "error": "Serial port not connected"}, 503`.
   - If `esp32_wifi`: make HTTP call with timeout, check `resp.status_code == 200`. If it fails or times out, return `{"success": False, "error": "ESP32 camera unreachable"}, 502`.
   - Only update `config["flash_state"]` when command delivery is verified.

**Step 4: Run tests to verify they pass**

Run: `python3 -m unittest backend/tests/test_api_security_and_validation.py -v`
Expected: PASS

**Step 5: Commit changes**

```bash
git add backend/app.py backend/tests/test_api_security_and_validation.py
git commit -m "fix(security): bind Flask to loopback, validate API inputs, and verify hardware flash ACK"
```

---

### Task 4: ESP32 Firmware Access Point Security & Endpoint Authorization

**Files:**
- Modify: `firmware/esp32_cam_streamer/esp32_cam_streamer.ino:18-35, 50-155, 230-238`

**Step 1: Review firmware security gaps and define changes**

- Finding S-02: Open SSID `ESP32-CAM-Vision` without a password allows any nearby device to join and hijack the stream/flash.
- Finding S-02: Control endpoints (`/led`, `/capture`, `/status`) have wildcard CORS and zero authentication.
- Fix:
  1. Add preprocessor/configurable AP password (minimum 8 characters, e.g. `ArgusVisionSecured`).
  2. Implement an authorization token header or query parameter check (`auth_token` or `X-Argus-Key`).
  3. Change `/led` method from `HTTP_GET` to `HTTP_POST` (or require auth token) to avoid state change via GET.
  4. Restrict CORS header to local dashboard origins or remove wildcard.

**Step 2: Update `firmware/esp32_cam_streamer/esp32_cam_streamer.ino`**

1. Set default secure WPA2 passphrase:
   ```cpp
   const char* ap_ssid = "ESP32-CAM-Vision";
   const char* ap_password = "ArgusVision2026!"; // WPA2-PSK secured
   const char* api_auth_key = "argus_secure_key"; // Authorization key
   ```
2. Add auth verification helper:
   ```cpp
   bool is_authorized(httpd_req_t *req) {
     char buf[64];
     if (httpd_req_get_hdr_value_str(req, "X-Argus-Key", buf, sizeof(buf)) == ESP_OK) {
       if (strcmp(buf, api_auth_key) == 0) return true;
     }
     if (httpd_req_get_url_query_len(req) > 0) {
       if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
         char key_val[32];
         if (httpd_query_key_value(buf, "key", key_val, sizeof(key_val)) == ESP_OK) {
           if (strcmp(key_val, api_auth_key) == 0) return true;
         }
       }
     }
     return false;
   }
   ```
3. Secure `/led` and `/capture` handlers to check `is_authorized(req)`:
   - If unauthorized, return `httpd_resp_send_err(req, HTTPD_401_UNAUTHORIZED, "Unauthorized")`.
4. Update `WiFi.softAP(ap_ssid, ap_password)` with channel and hidden options.
5. In `backend/app.py`, update `get_esp32_stream_url()` and flash HTTP request to include `key=argus_secure_key` or `X-Argus-Key` header.

**Step 3: Verify syntax and configuration consistency**

Ensure `backend/app.py` passes syntax compilation:
`python3 -m py_compile backend/app.py`

**Step 4: Commit changes**

```bash
git add firmware/esp32_cam_streamer/esp32_cam_streamer.ino backend/app.py
git commit -m "sec(firmware): secure ESP32 SoftAP with WPA2 passphrase and authorized control endpoints"
```

---

### Task 5: Frontend Portable API Config & Truthful Connection/Failure Feedback

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/LiveFeed.jsx`
- Modify: `frontend/src/components/ControlPanel.jsx`
- Modify: `frontend/src/components/Header.jsx`
- Modify: `frontend/src/components/SnapshotGallery.jsx`
- Create: `frontend/src/config.js`
- Modify: `frontend/vite.config.js`

**Step 1: Centralize API Base URL and Add Vite Proxy**

Create `frontend/src/config.js`:
```javascript
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
```
Update `frontend/vite.config.js` to configure a development proxy to `http://127.0.0.1:5000` so frontend calls `/api/*` and `/video_feed` relatively without hardcoded `localhost:5000`.

**Step 2: Update Frontend components to use `API_BASE_URL` and truthful error states**

1. In `frontend/src/App.jsx`:
   - Replace hardcoded `http://localhost:5000` with `API_BASE_URL` paths.
   - Read `stats.selected_source`, `stats.active_source`, `stats.connected`, and `stats.source_error`.
   - In `handleFlashToggle`, check `res.ok`. If false, display an error toast/indicator ("Hardware unreachable") instead of optimistically assuming synchronization.
   - Include `standby` option in Source selection.
2. In `frontend/src/components/LiveFeed.jsx`:
   - Use relative or `API_BASE_URL` stream URLs.
   - Display a distinct, truthful HUD indicator when in `standby` or when `!stats.connected`, explaining that no hardware frame is being received.
   - Never show "Connected" if `active_source` is null.
3. In `frontend/src/components/ControlPanel.jsx`:
   - Check API responses (`response.ok`) before declaring settings synchronized.
   - Add "Standby (No Camera)" option so user can safely stop streaming.

**Step 3: Verify frontend builds and lints**

Run: `cd frontend && npm run build`
Expected: PASS with zero build errors.

**Step 4: Commit changes**

```bash
git add frontend/
git commit -m "feat(frontend): make API URL configurable and surface truthful connection failures"
```

---

### Task 6: End-to-End Phase 1 Verification Test Suite

**Files:**
- Create: `backend/tests/test_phase1_e2e.py`
- Modify: `start.sh`

**Step 1: Write integration test covering Phase 1 truth and safety guarantees**

Create `backend/tests/test_phase1_e2e.py`:
1. Verify `/api/stats` returns accurate telemetry with no silent screen fallback when hardware is disconnected.
2. Verify `/api/config` strictly validates payloads and rejects malicious or invalid inputs.
3. Verify `/api/flash` returns failure when hardware is disconnected.
4. Verify `/video_feed` yields standby frame when selected source is disconnected.

**Step 2: Run all Phase 1 tests**

Run: `python3 -m unittest discover backend/tests -v`
Expected: ALL TESTS PASS.

**Step 3: Update `start.sh` for reliable health checks**

Update `start.sh` to fail fast with informative diagnostics if backend health is unreachable within the timeout, rather than prematurely declaring "fully live".

**Step 4: Commit changes**

```bash
git add backend/tests/ start.sh
git commit -m "test(phase1): add end-to-end verification suite and robust startup health checking"
```

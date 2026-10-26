import os
import sys
import unittest
from unittest.mock import patch, MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

class TestPhase1E2E(unittest.TestCase):
    def setUp(self):
        import app as app_module
        self.app = app_module
        self.client = app_module.app.test_client()
        self.app.config["source_type"] = "standby"

    def tearDown(self):
        self.app.config["source_type"] = "standby"

    def test_default_telemetry_truthfulness(self):
        res = self.client.get('/api/stats')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("selected_source"), "standby")
        self.assertIsNone(data.get("active_source"))
        self.assertFalse(data.get("connected"))

    def test_hardware_disconnected_reports_false_connection(self):
        # Select usb_serial when no device is plugged in
        res = self.client.post('/api/config', json={"source_type": "usb_serial"})
        self.assertEqual(res.status_code, 200)

        # Telemetry must show connected = False and active_source = None
        self.app.active_source = None
        self.app.source_connected = False
        self.app.source_error = "Serial port COM9 closed or unavailable"

        stats_res = self.client.get('/api/stats')
        stats = stats_res.get_json()
        self.assertEqual(stats.get("selected_source"), "usb_serial")
        self.assertIsNone(stats.get("active_source"))
        self.assertFalse(stats.get("connected"))
        self.assertIn("unavailable", stats.get("source_error", ""))

    def test_unauthorized_source_types_rejected(self):
        res = self.client.post('/api/config', json={"source_type": "arbitrary_device"})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get("success", True))

    def test_ssrf_metadata_ip_rejected(self):
        res = self.client.post('/api/config', json={"esp32_ip": "169.254.169.254"})
        self.assertEqual(res.status_code, 400)

    def test_flash_hardware_acknowledgment(self):
        # Setting flash on disconnected Wi-Fi ESP32 must fail truthfully
        self.client.post('/api/config', json={"source_type": "esp32_wifi"})
        with patch('app.requests.get', side_effect=Exception("Host unreachable")):
            res = self.client.post('/api/flash', json={"state": True, "brightness": 255})
            self.assertIn(res.status_code, [502, 503])
            data = res.get_json()
            self.assertFalse(data.get("success", True))

    def test_manual_capture_unique_filename(self):
        # Capture should generate collision-resistant names
        res1 = self.client.post('/api/capture')
        if res1.status_code == 200:
            name1 = res1.get_json().get("filename")
            res2 = self.client.post('/api/capture')
            name2 = res2.get_json().get("filename")
            self.assertNotEqual(name1, name2)

if __name__ == '__main__':
    unittest.main()

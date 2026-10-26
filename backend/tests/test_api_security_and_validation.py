import os
import sys
import unittest
from unittest.mock import patch, MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

class TestApiSecurityAndValidation(unittest.TestCase):
    def setUp(self):
        import app as app_module
        self.app_module = app_module
        self.client = app_module.app.test_client()
        self.app_module.config["source_type"] = "standby"

    def tearDown(self):
        self.app_module.config["source_type"] = "standby"

    def test_config_invalid_source_rejected(self):
        res = self.client.post('/api/config', json={"source_type": "invalid_source"})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get("success", False))
        self.assertIn("error", data)

    def test_config_valid_source_accepted(self):
        res = self.client.post('/api/config', json={"source_type": "standby"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success", False))

    def test_config_invalid_mode_rejected(self):
        res = self.client.post('/api/config', json={"mode": "nonexistent_mode"})
        self.assertEqual(res.status_code, 400)

    def test_config_invalid_motion_threshold_rejected(self):
        res = self.client.post('/api/config', json={"motion_threshold": 9999})
        self.assertEqual(res.status_code, 400)

    def test_flash_fails_when_hardware_unreachable(self):
        self.app_module.config["source_type"] = "esp32_wifi"
        # Mock requests.get to simulate connection timeout/error to ESP32
        with patch('app.requests.get', side_effect=Exception("Connection refused")):
            res = self.client.post('/api/flash', json={"state": True, "brightness": 200})
            self.assertIn(res.status_code, [502, 503])
            data = res.get_json()
            self.assertFalse(data.get("success", True))
            self.assertIn("error", data)

    def test_flash_fails_when_serial_port_not_open(self):
        self.app_module.config["source_type"] = "usb_serial"
        with patch('app.get_serial_connection', return_value=None):
            res = self.client.post('/api/flash', json={"state": True, "brightness": 200})
            self.assertIn(res.status_code, [502, 503])
            data = res.get_json()
            self.assertFalse(data.get("success", True))

if __name__ == '__main__':
    unittest.main()

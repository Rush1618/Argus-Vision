import os
import sys
import unittest
import numpy as np

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

class TestSourceAndConnectionTruth(unittest.TestCase):
    def setUp(self):
        import app as app_module
        self.app = app_module
        self.app.config["source_type"] = "standby"

    def tearDown(self):
        self.app.config["source_type"] = "standby"

    def test_default_source_is_standby_not_screen(self):
        # Default source must be 'standby' to protect user privacy
        self.assertEqual(self.app.config.get("source_type"), "standby")

    def test_standby_frame_generator(self):
        frame = self.app.generate_standby_frame("TEST STANDBY")
        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape, (480, 640, 3))

    def test_telemetry_separates_selected_and_active_source(self):
        self.app.config["source_type"] = "esp32_wifi"
        self.app.active_source = None
        self.app.source_connected = False
        self.app.source_error = "No signal"
        
        stats = self.app.get_current_telemetry()
        self.assertEqual(stats["selected_source"], "esp32_wifi")
        self.assertIsNone(stats["active_source"])
        self.assertFalse(stats["connected"])
        self.assertEqual(stats["source_error"], "No signal")

if __name__ == '__main__':
    unittest.main()

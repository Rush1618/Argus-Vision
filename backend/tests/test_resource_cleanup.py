import os
import sys
import unittest
from unittest.mock import MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

class TestResourceCleanup(unittest.TestCase):
    def setUp(self):
        import app as app_module
        self.app = app_module

    def test_cleanup_previous_source_releases_handles(self):
        mock_cap = MagicMock()
        mock_response = MagicMock()
        mock_serial = MagicMock()

        self.app.release_source_resources(mock_cap, mock_response, mock_serial)

        mock_cap.release.assert_called_once()
        mock_response.close.assert_called_once()
        mock_serial.close.assert_called_once()

    def test_cleanup_handles_none_gracefully(self):
        # Should not throw any exception when handles are None
        try:
            self.app.release_source_resources(None, None, None)
        except Exception as e:
            self.fail(f"release_source_resources raised {e} with None handles")

if __name__ == '__main__':
    unittest.main()

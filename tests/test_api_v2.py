import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app

class TestApiV2(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.outages.router_v2.yasno_service.resolve_street_id", new_callable=AsyncMock)
    @patch("app.outages.router_v2.yasno_service.resolve_house_id", new_callable=AsyncMock)
    @patch("app.outages.router_v2.outage_service.get_status", new_callable=AsyncMock)
    def test_websocket_stream_grid_updates(self, mock_get_status, mock_resolve_house, mock_resolve_street):
        # 1. Mock service resolutions
        mock_resolve_street.return_value = (12, "вул. Вишнева")
        mock_resolve_house.return_value = (34, "1")
        mock_get_status.return_value = {
            "power_status": "ON",
            "status_reason": "Stable power"
        }

        # 3. Connect via WebSocket and resolve address statuses
        with self.client.websocket_connect("/api/v2/ws/outages") as websocket:
            websocket.send_json({
                "action": "resolve_statuses",
                "addresses": [
                    {"street": "Вишнева", "house": "1"}
                ]
            })
            
            # Message 1: progressive status update response
            msg = websocket.receive_json()
            self.assertEqual(msg["type"], "status_update")
            self.assertEqual(msg["street"], "Вишнева")
            self.assertEqual(msg["house"], "1")
            self.assertEqual(msg["status"], "ON")
            self.assertEqual(msg["reason"], "Stable power")

    def test_get_websocket_info(self):
        # We override standard JSON serialization validation check
        response = self.client.get("/api/v2/ws/info")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["websocket_url"], "/api/v2/ws/outages")
        self.assertEqual(response.json()["protocol"], "JSON")

if __name__ == "__main__":
    unittest.main()

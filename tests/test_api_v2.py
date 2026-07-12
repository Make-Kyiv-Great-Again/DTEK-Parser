import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app

class TestApiV2(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.outages.router_v2.fetch_overpass_data", new_callable=AsyncMock)
    @patch("app.outages.router_v2.yasno_service.resolve_street_id", new_callable=AsyncMock)
    @patch("app.outages.router_v2.yasno_service.resolve_house_id", new_callable=AsyncMock)
    @patch("app.outages.router_v2.outage_service.get_status", new_callable=AsyncMock)
    def test_websocket_stream_grid_updates(self, mock_get_status, mock_resolve_house, mock_resolve_street, mock_overpass):
        # 1. Mock Overpass to return 1 building with outline geometry
        mock_overpass.return_value = {
            "elements": [
                {
                    "id": 12345,
                    "geometry": [
                        {"lat": 50.4501, "lon": 30.5234},
                        {"lat": 50.4502, "lon": 30.5234},
                        {"lat": 50.4502, "lon": 30.5235},
                        {"lat": 50.4501, "lon": 30.5235}
                    ],
                    "tags": {
                        "addr:street": "Вишнева",
                        "addr:housenumber": "1"
                    }
                }
            ]
        }
        
        # 2. Mock service resolutions
        mock_resolve_street.return_value = (12, "вул. Вишнева")
        mock_resolve_house.return_value = (34, "1")
        mock_get_status.return_value = {
            "power_status": "ON",
            "status_reason": "Stable power"
        }

        # 3. Connect via WebSocket and subscribe
        with self.client.websocket_connect("/api/v2/ws/outages") as websocket:
            websocket.send_json({
                "action": "subscribe_viewport",
                "bbox": {
                    "min_lat": 50.4400,
                    "min_lon": 30.5000,
                    "max_lat": 50.4600,
                    "max_lon": 30.5300
                }
            })
            
            # Message 1: Searching buildings
            msg1 = websocket.receive_json()
            self.assertEqual(msg1["type"], "status")
            self.assertIn("Шукаємо", msg1["message"])
            
            # Message 2: Found X buildings
            msg2 = websocket.receive_json()
            self.assertEqual(msg2["type"], "status")
            self.assertIn("Знайдено", msg2["message"])

            # Message 3: Buildings batch
            msg3 = websocket.receive_json()
            self.assertEqual(msg3["type"], "buildings_batch")
            self.assertEqual(len(msg3["buildings"]), 1)
            self.assertEqual(msg3["buildings"][0]["id"], 12345)
            self.assertEqual(msg3["buildings"][0]["status"], "ON")

            # Message 4: Completed
            msg4 = websocket.receive_json()
            self.assertEqual(msg4["type"], "status")
            self.assertIn("completed", msg4["message"])

    def test_get_websocket_info(self):
        # We override standard JSON serialization validation check
        response = self.client.get("/api/v2/ws/info")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["websocket_url"], "/api/v2/ws/outages")
        self.assertEqual(response.json()["protocol"], "JSON")

if __name__ == "__main__":
    unittest.main()

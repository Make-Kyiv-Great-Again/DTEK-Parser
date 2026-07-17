import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.exceptions import ClientConnectionError, ClientResponseError

class TestPlacesApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.places.router.places_service.get_nearby_places", new_callable=AsyncMock)
    def test_get_nearby_places_success(self, mock_get_places):
        # Setup mock return value
        mock_get_places.return_value = [
            {
                "id": 12345,
                "type": "cafe",
                "lat": 50.4501,
                "lng": 30.5234,
                "name": "Золотий Дукат",
                "metadata": {
                    "cuisine": "coffee_shop",
                    "opening_hours": "09:00-21:00"
                }
            }
        ]

        response = self.client.get("/api/v1/nearby?lat=50.4501&lng=30.5234&radius=500")
        self.assertEqual(response.status_code, 200)
        
        json_data = response.json()
        self.assertEqual(len(json_data), 1)
        self.assertEqual(json_data[0]["id"], 12345)
        self.assertEqual(json_data[0]["type"], "cafe")
        self.assertEqual(json_data[0]["name"], "Золотий Дукат")
        self.assertEqual(json_data[0]["metadata"]["cuisine"], "coffee_shop")

    def test_get_nearby_places_invalid_input(self):
        # 1. Invalid Latitude
        response = self.client.get("/api/v1/nearby?lat=95.0&lng=30.5234&radius=500")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Latitude must be between", response.json()["detail"])

        # 2. Invalid Longitude
        response = self.client.get("/api/v1/nearby?lat=50.4501&lng=-190.0&radius=500")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Longitude must be between", response.json()["detail"])

        # 3. Invalid Radius
        response = self.client.get("/api/v1/nearby?lat=50.4501&lng=30.5234&radius=-100")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Radius must be a positive integer", response.json()["detail"])

    @patch("app.places.client.overpass_client.fetch_nearby_nodes", new_callable=AsyncMock)
    def test_places_service_and_client_integration(self, mock_fetch_nodes):
        # Mock raw Overpass response elements
        mock_fetch_nodes.return_value = {
            "elements": [
                {
                    "type": "node",
                    "id": 98765,
                    "lat": 50.4510,
                    "lon": 30.5240,
                    "tags": {
                        "amenity": "restaurant",
                        "name": "Кафе Ярослава",
                        "cuisine": "ukrainian",
                        "website": "https://yaroslava.ua"
                    }
                },
                {
                    "type": "node",
                    "id": 11122,
                    "lat": 50.4520,
                    "lon": 30.5250,
                    "tags": {
                        "shop": "supermarket",
                        "name": "Сільпо",
                        "opening_hours": "08:00-23:00"
                    }
                }
            ]
        }

        # Query endpoint (which triggers router -> service -> mocked client)
        response = self.client.get("/api/v1/nearby?lat=50.4500&lng=30.5230&radius=1000")
        self.assertEqual(response.status_code, 200)

        json_data = response.json()
        self.assertEqual(len(json_data), 2)

        # First place (restaurant)
        self.assertEqual(json_data[0]["id"], 98765)
        self.assertEqual(json_data[0]["type"], "restaurant")
        self.assertEqual(json_data[0]["name"], "Кафе Ярослава")
        self.assertEqual(json_data[0]["metadata"]["cuisine"], "ukrainian")
        self.assertEqual(json_data[0]["metadata"]["website"], "https://yaroslava.ua")
        self.assertNotIn("name", json_data[0]["metadata"])

        # Second place (shop)
        self.assertEqual(json_data[1]["id"], 11122)
        self.assertEqual(json_data[1]["type"], "supermarket")
        self.assertEqual(json_data[1]["name"], "Сільпо")
        self.assertEqual(json_data[1]["metadata"]["opening_hours"], "08:00-23:00")
        self.assertNotIn("shop", json_data[1]["metadata"])

    @patch("app.places.client.overpass_client.fetch_nearby_nodes", new_callable=AsyncMock)
    def test_overpass_gateway_timeout(self, mock_fetch_nodes):
        mock_fetch_nodes.side_effect = ClientConnectionError("Gateway Timeout: Request to Overpass container timed out")
        
        response = self.client.get("/api/v1/nearby?lat=50.4500&lng=30.5230")
        self.assertEqual(response.status_code, 504)
        self.assertIn("Gateway Timeout", response.json()["detail"])

if __name__ == "__main__":
    unittest.main()

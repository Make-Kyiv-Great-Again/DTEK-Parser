import unittest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from app.main import app
from app.core.exceptions import AddressNotFoundError, InvalidInputError, GeocodingError

class TestApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_regions(self):
        with patch("app.services.yasno_service.yasno_service.get_regions", new_callable=AsyncMock) as mock_regions:
            mock_regions.return_value = [
                {"id": 25, "value": "Київ", "hasCities": False, "dsos": []}
            ]
            response = self.client.get("/api/v1/regions")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [{"id": 25, "value": "Київ", "hasCities": False, "dsos": []}])

    def test_get_status_success(self):
        with patch("app.services.outage_service.outage_service.get_status", new_callable=AsyncMock) as mock_get_status:
            mock_get_status.return_value = {
                "region_id": 25,
                "street_id": 152,
                "house_id": 14943,
                "dso_id": 902,
                "address": "Група 1",
                "group_info": {"group": 1, "subgroup": 1, "raw_group_key": "1.1", "mapped_group_key": "1.1"},
                "power_status": "ON",
                "status_reason": "Світло є",
                "planned_schedule": None,
                "weekly_schedule": None,
                "has_power": True,
                "group": "1.1",
                "last_update": None
            }
            response = self.client.get("/api/v1/status?streetName=Вишнева&houseName=1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["power_status"], "ON")
            self.assertEqual(response.json()["has_power"], True)

    def test_get_status_address_not_found(self):
        with patch("app.services.outage_service.outage_service.get_status", new_callable=AsyncMock) as mock_get_status:
            mock_get_status.side_effect = AddressNotFoundError("Street not found")
            response = self.client.get("/api/v1/status?streetName=Unknown&houseName=1")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"detail": "Street not found"})

    def test_get_status_invalid_input(self):
        with patch("app.services.outage_service.outage_service.get_status", new_callable=AsyncMock) as mock_get_status:
            mock_get_status.side_effect = InvalidInputError("Missing params")
            response = self.client.get("/api/v1/status")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"detail": "Missing params"})

    def test_get_status_by_coordinates_geocoding_error(self):
        with patch("app.services.outage_service.outage_service.get_status_by_coordinates", new_callable=AsyncMock) as mock_coords:
            mock_coords.side_effect = GeocodingError("Nominatim error")
            response = self.client.get("/api/v1/status/coordinates?lat=50.0&lon=30.0")
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json(), {"detail": "Nominatim error"})

if __name__ == "__main__":
    unittest.main()

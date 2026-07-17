import unittest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from app.main import app
from app.core.exceptions import AddressNotFoundError, InvalidInputError, GeocodingError

class TestApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_regions(self):
        with patch("app.yasno.router.yasno_service.get_regions", new_callable=AsyncMock) as mock_regions:
            mock_regions.return_value = [
                {"id": 25, "value": "Київ", "hasCities": False, "dsos": []}
            ]
            response = self.client.get("/api/v1/regions")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [{"id": 25, "value": "Київ", "hasCities": False, "dsos": []}])

    def test_get_status_success(self):
        with patch("app.outages.router.outage_service.get_status", new_callable=AsyncMock) as mock_get_status:
            mock_get_status.return_value = {
                "region_id": 25,
                "street_id": 152,
                "house_id": 14943,
                "dso_id": 902,
                "region_name": "Київ",
                "street_name": "Вишнева",
                "house_name": "1",
                "group_assignment": {
                    "group": 1,
                    "subgroup": 1,
                    "raw_group_key": "1.1",
                    "mapped_group_key": "1.1"
                },
                "power_status": "ON",
                "status_reason": "Світло є",
                "planned_schedule": {
                    "today": None,
                    "tomorrow": None,
                    "updatedOn": None
                },
                "weekly_schedule": None,
                "has_power": True,
                "group": "1.1",
                "last_update": "2026-07-11T12:00:00"
            }
            response = self.client.get("/api/v1/status?regionId=25&streetName=Вишнева&houseName=1&dsoId=902")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["power_status"], "ON")
            self.assertEqual(response.json()["has_power"], True)

    def test_get_status_address_not_found(self):
        with patch("app.outages.router.yasno_service.resolve_street_id", new_callable=AsyncMock) as mock_resolve_street:
            mock_resolve_street.side_effect = AddressNotFoundError("Street not found")
            response = self.client.get("/api/v1/status?regionId=25&streetName=Unknown&houseName=1&dsoId=902")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"detail": "Street not found"})

    def test_get_status_invalid_input(self):
        response = self.client.get("/api/v1/status")
        # Missing Query parameters returns 422 Unprocessable Entity in FastAPI automatically
        self.assertEqual(response.status_code, 422)

    def test_get_status_by_coordinates_geocoding_error(self):
        with patch("app.outages.router.outage_service.get_status_by_coordinates", new_callable=AsyncMock) as mock_coords:
            mock_coords.side_effect = GeocodingError("Nominatim error")
            response = self.client.get("/api/v1/status/coordinates?lat=50.0&lon=30.0")
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json(), {"detail": "Nominatim error"})

    @patch("app.dtek.router.dtek_service.get_viewport_outages", new_callable=AsyncMock)
    def test_get_dtek_viewport_outages_success(self, mock_get_viewport):
        mock_get_viewport.return_value = {
            "вулиця Хрещатик": {
                "18": { "status": "ON", "details": "DTEK Live: Power is active." },
                "20": { "status": "OFF", "details": "DTEK Live: Active Outage (10:00 - 14:00)" }
            }
        }
        
        response = self.client.get("/api/v1/dtek/viewport?lat_top=50.4501&lon_left=30.5230&lat_bottom=50.4490&lon_right=30.5250")
        self.assertEqual(response.status_code, 200)
        
        json_data = response.json()
        self.assertIn("вулиця Хрещатик", json_data)
        self.assertEqual(json_data["вулиця Хрещатик"]["18"]["status"], "ON")
        self.assertEqual(json_data["вулиця Хрещатик"]["20"]["status"], "OFF")

    def test_get_dtek_viewport_outages_invalid_input(self):
        # Invalid Latitude boundary
        response = self.client.get("/api/v1/dtek/viewport?lat_top=95.0&lon_left=30.5230&lat_bottom=50.4490&lon_right=30.5250")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Latitude coordinate", response.json()["detail"])

        # Invalid Longitude boundary
        response = self.client.get("/api/v1/dtek/viewport?lat_top=50.4501&lon_left=-190.0&lat_bottom=50.4490&lon_right=30.5250")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Longitude coordinate", response.json()["detail"])

if __name__ == "__main__":
    unittest.main()

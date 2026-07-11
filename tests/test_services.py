import unittest
from unittest.mock import AsyncMock, patch
from app.services.dtek_service import dtek_service
from app.services.yasno_service import yasno_service
from app.services.outage_service import outage_service
from app.core.exceptions import AddressNotFoundError

class TestServices(unittest.IsolatedAsyncioTestCase):
    def test_dtek_service_find_matched_house(self):
        dtek_data = {
            "12-б": {"type": "Definite", "start_date": "10:00", "end_date": "14:00"},
            "14": {"type": "", "start_date": "", "end_date": ""}
        }
        matched = dtek_service.find_matched_house("12б", dtek_data)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["type"], "Definite")

        status, reason = dtek_service.extract_power_status(matched)
        self.assertEqual(status, "OFF")
        self.assertIn("10:00", reason)

    def test_dtek_service_no_match(self):
        dtek_data = {"12-б": {"type": "Definite"}}
        matched = dtek_service.find_matched_house("15", dtek_data)
        self.assertIsNone(matched)

    @patch("app.services.yasno_client.yasno_client.search_streets", new_callable=AsyncMock)
    async def test_yasno_service_resolve_street_success(self, mock_search):
        mock_search.return_value = [{"id": 100, "value": "вул. Тестова"}]
        street_id, name = await yasno_service.resolve_street_id(25, "Тестова", 902)
        self.assertEqual(street_id, 100)
        self.assertEqual(name, "вул. Тестова")

    @patch("app.services.yasno_client.yasno_client.search_streets", new_callable=AsyncMock)
    async def test_yasno_service_resolve_street_not_found(self, mock_search):
        mock_search.return_value = []
        with self.assertRaises(AddressNotFoundError):
            await yasno_service.resolve_street_id(25, "Unknown", 902)

    def test_compute_scheduled_status_emergency(self):
        planned_data = {
            "today": {"status": "EmergencyOutages", "slots": []}
        }
        status, reason = outage_service.compute_scheduled_status(planned_data, None, "1.1")
        self.assertEqual(status, "EMERGENCY")
        self.assertIn("Emergency", reason)

    def test_compute_scheduled_status_no_outages(self):
        planned_data = {
            "today": {"status": "NoOutages", "slots": []}
        }
        status, reason = outage_service.compute_scheduled_status(planned_data, None, "1.1")
        self.assertEqual(status, "ON")
        self.assertIn("No active", reason)

if __name__ == "__main__":
    unittest.main()

import logging
from typing import Dict, Any, Optional, Tuple
from app.dtek.client import dtek_client
from app.utils.normalization import normalize_house

logger = logging.getLogger(__name__)

class DtekService:
    async def get_live_street_data(self, dso_id: int, city: str, street: str) -> Dict[str, Any]:
        """
        Queries DTEK live AJAX endpoint for the given street name.
        Returns a dict of house numbers mapping to their schedule status, or empty dict if not found.
        """
        try:
            live_resp = await dtek_client.fetch_live_status(dso_id, city, street)
            html_content = live_resp.get("html", "")
            return self.parse_dtek_houses_html(html_content)
        except Exception as e:
            logger.warning(f"Failed to fetch live DTEK status for street '{street}': {e}")
            return {}

    def parse_dtek_houses_html(self, html: str) -> Dict[str, Any]:
        """Parses DTEK's Yii HTML markup table of houses, returning a structured schedule status dictionary."""
        from bs4 import BeautifulSoup
        if not html:
            return {}
            
        soup = BeautifulSoup(html, "html.parser")
        houses_data = {}
        
        # Iterate over all table rows containing house statuses
        for row in soup.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 3:
                # Column 1: House Number (e.g. "12б" or "14/1")
                house_num = cols[0].get_text(strip=True)
                
                # Column 2: Status Tag / Outage Group Type (e.g. contains "definite", "possible", "off" style markers)
                status_cell = cols[1]
                outage_type = ""
                classes = status_cell.get("class", [])
                if any("definite" in c.lower() for c in classes) or status_cell.find(class_=re_class_check("definite")):
                    outage_type = "Definite"
                elif any("possible" in c.lower() for c in classes) or status_cell.find(class_=re_class_check("possible")):
                    outage_type = "Possible"
                elif any("no-outage" in c.lower() for c in classes) or status_cell.find(class_=re_class_check("no-outage")):
                    outage_type = "NoOutage"

                # Column 3: Outage Schedule/Reason details text (e.g. "09:00 - 13:00")
                schedule_details = cols[2].get_text(strip=True)
                
                # Check for direct class names on td elements
                if not outage_type:
                    text_lower = status_cell.get_text(strip=True).lower()
                    if "немає" in text_lower or "відсутня" in text_lower:
                        outage_type = "Definite"
                    elif "можливе" in text_lower or "ймовірне" in text_lower:
                        outage_type = "Possible"
                    else:
                        outage_type = "NoOutage"

                # Parse specific time ranges
                start_date = ""
                end_date = ""
                time_match = re_time_search(schedule_details)
                if time_match:
                    start_date = time_match.group(1)
                    end_date = time_match.group(2)

                houses_data[house_num] = {
                    "type": outage_type,
                    "start_date": start_date,
                    "end_date": end_date,
                    "details": schedule_details
                }
                
        return houses_data

    def find_matched_house(self, house_name: str, dtek_houses: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Matches a target house string against DTEK's parsed dictionary keys using normalized matching."""
        target_norm = normalize_house(house_name)
        if not target_norm:
            return None

        # Check for exact matches
        for k, v in dtek_houses.items():
            if normalize_house(k) == target_norm:
                return v

        # Check for partial matches
        for k, v in dtek_houses.items():
            k_norm = normalize_house(k)
            if target_norm in k_norm or k_norm in target_norm:
                return v
                
        return None

    def extract_power_status(self, matched_house: Dict[str, Any]) -> Tuple[str, str]:
        """Maps DTEK live outage status to standard response strings."""
        outage_type = matched_house.get("type", "")
        details = matched_house.get("details", "")
        start = matched_house.get("start_date", "")
        end = matched_house.get("end_date", "")
        
        if outage_type == "Definite":
            reason = f"DTEK Live: Active Outage ({start} - {end})" if start else "DTEK Live: Active Outage"
            if details:
                reason += f" - {details}"
            return "OFF", reason
        elif outage_type == "Possible":
            reason = f"DTEK Live: Possible Outage ({start} - {end})" if start else "DTEK Live: Possible Outage"
            if details:
                reason += f" - {details}"
            return "PROBABLE", reason
            
        return "ON", "DTEK Live: Power is active."

    async def get_viewport_outages(
        self, lat_top: float, lon_left: float, lat_bottom: float, lon_right: float, dso_id: int, city: str
    ) -> Dict[str, Any]:
        """
        Retrieves all buildings with addresses within the specified bounding box from Overpass,
        then queries DTEK status concurrently for all unique streets in that viewport.
        """
        from app.places.client import overpass_client
        import asyncio

        min_lat = min(lat_top, lat_bottom)
        max_lat = max(lat_top, lat_bottom)
        min_lon = min(lon_left, lon_right)
        max_lon = max(lon_left, lon_right)

        # 1. Fetch buildings in bounding box from local Overpass instance
        query = f"""[out:json];
(
  node({min_lat},{min_lon},{max_lat},{max_lon})["addr:housenumber"]["addr:street"];
  way({min_lat},{min_lon},{max_lat},{max_lon})["addr:housenumber"]["addr:street"];
);
out center;"""

        try:
            raw_data = await overpass_client.query_overpass(query)
            elements = raw_data.get("elements", [])
        except Exception as e:
            logger.error(f"Failed to query local Overpass inside viewport: {e}")
            elements = []

        # 2. Group houses by street
        street_houses = {}
        for el in elements:
            tags = el.get("tags", {})
            street = tags.get("addr:street")
            house = tags.get("addr:housenumber")
            if street and house:
                if street not in street_houses:
                    street_houses[street] = set()
                street_houses[street].add(house)

        # 3. Query DTEK status concurrently for each street with a Semaphore
        sem = asyncio.Semaphore(5)

        async def fetch_street_status(street_name: str) -> Tuple[str, Dict[str, Any]]:
            async with sem:
                dtek_data = await self.get_live_street_data(dso_id, city, street_name)
                return street_name, dtek_data

        tasks = [fetch_street_status(street) for street in street_houses.keys()]
        if tasks:
            results = await asyncio.gather(*tasks)
            dtek_results_by_street = dict(results)
        else:
            dtek_results_by_street = {}

        # 4. Extrapolate statuses and structure final Option 2 payload
        response_payload = {}
        for street, houses in street_houses.items():
            street_payload = {}
            dtek_data = dtek_results_by_street.get(street, {})

            for house in sorted(houses):
                matched = self.find_matched_house(house, dtek_data)
                if matched:
                    status, reason = self.extract_power_status(matched)
                    street_payload[house] = {
                        "status": status,
                        "details": reason
                    }
                else:
                    # Default: no active outages reported
                    street_payload[house] = {
                        "status": "ON",
                        "details": "DTEK Live: No active outage reported."
                    }
            response_payload[street] = street_payload

        return response_payload

# Helper helpers
import re
def re_class_check(name: str):
    return re.compile(f".*{name}.*", re.IGNORECASE)

def re_time_search(text: str):
    # Regex to capture patterns like "10:00 - 14:00" or "10:00-14:00"
    return re.search(r'(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})', text)

dtek_service = DtekService()

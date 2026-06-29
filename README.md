# SvitloLocator - Yasno/DTEK Outage Map & API Wrapper

SvitloLocator is a clean FastAPI-based REST API wrapper and dark-themed interactive map frontend that queries real-time power outages directly from DTEK Kyiv/Dnipro regional AJAX services. It automatically bypasses WAF controls, extracts session CSRF tokens, and conditionally renders schedules in the UI only when outages are active or planned.

---

## 🚀 Quick Start (Using Docker)

1. **Build the Docker Image:**
   ```bash
   docker build -t svitlolocator .
   ```

2. **Run the Container:**
   ```bash
   docker run -d -p 8000:8082 --name svitlolocator svitlolocator
   ```

3. **Access the Map:**
   Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your web browser. Or you can read docs at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🛠️ API Reference

### All documentation available at: [http://localhost:8000/docs](http://localhost:8000/docs)

### 1. Retrieve Current Status: `GET /api/v1/status`
Queries the live status for a street and house. Falls back to static schedule calculations if names are omitted.

- **Parameters:**
  - `regionId` (int): Yasno region ID (e.g. `25` for Kyiv)
  - `dsoId` (int): DSO ID (e.g. `902` for DTEK Kyiv Grids)
  - `streetId` (int): Yasno street ID (e.g. `1010`)
  - `houseId` (int): Yasno house ID (e.g. `9760`)
  - `streetName` (string, optional): Full street name (e.g. `"вул. Хрещатик"`)
  - `houseName` (string, optional): House number (e.g. `"10"`)

- **Response Format:**
  ```json
  {
    "region_id": 25,
    "street_id": 1010,
    "house_id": 9760,
    "dso_id": 902,
    "address": "Група 20.1 (Графік 2.1)",
    "group_info": {
      "group": 20,
      "subgroup": 1,
      "raw_group_key": "20.1",
      "mapped_group_key": "2.1"
    },
    "power_status": "ON",
    "status_reason": "Світло є (відключення не зафіксовано)",
    "planned_schedule": { ... },
    "weekly_schedule": { ... },
    "has_power": true,
    "group": "20.1",
    "last_update": "00:48 29.06.2026"
  }
  ```

### 2. Autocomplete Streets: `GET /api/v1/streets`
- **Parameters:** `regionId` (int), `dsoId` (int), `query` (string)

### 3. Fetch Houses: `GET /api/v1/houses`
- **Parameters:** `regionId` (int), `dsoId` (int), `streetId` (int)

### 4. Query Status by Geographic Coordinates: `GET /api/v1/status/coordinates`
Reverse-geocodes coordinate values to find the matching street and house, then retrieves live outage status.

- **Parameters:**
  - `lat` (float): Latitude (e.g. `50.4462`)
  - `lon` (float): Longitude (e.g. `30.5208`)

- **Response:** Same payload schema as `GET /api/v1/status`.

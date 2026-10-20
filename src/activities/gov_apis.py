import logging
import json
import asyncio
from typing import List, Optional, Dict, Any
import urllib.request
import urllib.parse
from src.models.domain import NHTSARecall, NHTSAComplaint, EPAFuelEconomy

logger = logging.getLogger(__name__)

NHTSA_VPIC_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"
NHTSA_API_URL = "https://api.nhtsa.gov"
EPA_API_URL = "https://www.fueleconomy.gov/ws/rest"

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class GovAPIClient:
    """Client for querying NHTSA safety, recalls, complaints, and EPA fuel economy data."""

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "CarResearcherPipeline/1.0",
        }

    async def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch JSON via httpx if available, falling back to urllib."""
        if params:
            query_str = urllib.parse.urlencode(params)
            sep = "&" if "?" in url else "?"
            full_url = f"{url}{sep}{query_str}"
        else:
            full_url = url

        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(full_url, headers=self.headers)
                resp.raise_for_status()
                return resp.json()
        else:
            def _fetch_sync() -> Dict[str, Any]:
                req = urllib.request.Request(full_url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))

            return await asyncio.to_thread(_fetch_sync)

    async def decode_vin(self, vin: str) -> Dict[str, Any]:
        """Decode a 17-character VIN via NHTSA vPIC API."""
        url = f"{NHTSA_VPIC_URL}/DecodeVin/{vin}?format=json"
        data = await self._get_json(url)
        results = data.get("Results", [])
        decoded = {}
        for item in results:
            variable = item.get("Variable")
            value = item.get("Value")
            if variable and value:
                decoded[variable] = value
        return decoded

    async def get_recalls(self, make: str, model: str, year: int) -> List[NHTSARecall]:
        """Fetch all official safety recalls from NHTSA for a specific make, model, and year."""
        url = f"{NHTSA_API_URL}/recalls/recallsByVehicle"
        params = {"make": make, "model": model, "modelYear": year}

        try:
            data = await self._get_json(url, params=params)
        except Exception as e:
            logger.error(f"Failed to fetch NHTSA recalls for {year} {make} {model}: {e}")
            return []

        recalls: List[NHTSARecall] = []
        raw_results = data.get("results", []) or []
        for r in raw_results:
            recalls.append(
                NHTSARecall(
                    campaign_number=r.get("NHTSACampaignNumber", "UNKNOWN"),
                    component=r.get("Component", "Unknown"),
                    summary=r.get("Summary", ""),
                    consequence=r.get("Conequence", r.get("Consequence", "")),
                    remedy=r.get("Remedy", ""),
                    report_date=r.get("ReportReceivedDate"),
                    notes=r.get("Notes"),
                )
            )
        return recalls

    async def get_complaints(self, make: str, model: str, year: int) -> List[NHTSAComplaint]:
        """Fetch consumer safety complaints filed with NHTSA."""
        url = f"{NHTSA_API_URL}/complaints/complaintsByVehicle"
        params = {"make": make, "model": model, "modelYear": year}

        try:
            data = await self._get_json(url, params=params)
        except Exception as e:
            logger.error(f"Failed to fetch NHTSA complaints for {year} {make} {model}: {e}")
            return []

        complaints: List[NHTSAComplaint] = []
        raw_results = data.get("results", []) or []
        for c in raw_results:
            complaints.append(
                NHTSAComplaint(
                    odi_number=str(c.get("odiNumber", "")),
                    component=c.get("components", "Unknown"),
                    summary=c.get("summary", ""),
                    crash=bool(c.get("crash", False)),
                    fire=bool(c.get("fire", False)),
                    number_of_injuries=int(c.get("numberOfInjuries", 0) or 0),
                    number_of_deaths=int(c.get("numberOfDeaths", 0) or 0),
                    date_filed=c.get("dateOfIncident"),
                )
            )
        return complaints

    async def get_epa_fuel_economy(self, make: str, model: str, year: int) -> List[EPAFuelEconomy]:
        """Fetch EPA fuel economy, MPGe, and EV range benchmarks."""
        url = f"{EPA_API_URL}/vehicle/menu/options"
        params = {"year": year, "make": make, "model": model}

        try:
            data = await self._get_json(url, params=params)
        except Exception as e:
            logger.error(f"Failed to fetch EPA options for {year} {make} {model}: {e}")
            return []

        menu_items = data.get("menuItem", [])
        if isinstance(menu_items, dict):
            menu_items = [menu_items]

        results: List[EPAFuelEconomy] = []
        for item in menu_items:
            vehicle_id = item.get("value")
            if not vehicle_id:
                continue

            detail_url = f"{EPA_API_URL}/vehicle/{vehicle_id}"
            try:
                detail = await self._get_json(detail_url)
                results.append(
                    EPAFuelEconomy(
                        vehicle_id=str(vehicle_id),
                        make=make,
                        model=model,
                        year=year,
                        comb_mpge=float(detail.get("comb08", 0) or 0) or None,
                        city_mpge=float(detail.get("city08", 0) or 0) or None,
                        hwy_mpge=float(detail.get("highway08", 0) or 0) or None,
                        range_miles=int(detail.get("range", 0) or 0) or None,
                        annual_fuel_cost=int(detail.get("fuelCost08", 0) or 0) or None,
                        fuel_type=detail.get("fuelType", "Electricity"),
                        raw_specs=detail,
                    )
                )
            except Exception as detail_err:
                logger.warning(f"Failed to fetch EPA vehicle details for id {vehicle_id}: {detail_err}")

        return results


# -------------------------------------------------------------
# Temporal Activity Wrappers
# -------------------------------------------------------------
async def fetch_nhtsa_recalls_activity(make: str, model: str, year: int) -> List[Dict[str, Any]]:
    client = GovAPIClient()
    recalls = await client.get_recalls(make, model, year)
    return [r.__dict__ for r in recalls]


async def fetch_nhtsa_complaints_activity(make: str, model: str, year: int) -> List[Dict[str, Any]]:
    client = GovAPIClient()
    complaints = await client.get_complaints(make, model, year)
    return [c.__dict__ for c in complaints]


async def fetch_epa_data_activity(make: str, model: str, year: int) -> List[Dict[str, Any]]:
    client = GovAPIClient()
    epa_list = await client.get_epa_fuel_economy(make, model, year)
    return [e.__dict__ for e in epa_list]


async def decode_vin_activity(vin: str) -> Dict[str, Any]:
    client = GovAPIClient()
    return await client.decode_vin(vin)

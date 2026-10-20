import pytest
from unittest.mock import AsyncMock, patch
from src.activities.gov_apis import GovAPIClient


@pytest.mark.asyncio
async def test_decode_vin_parsing():
    mock_payload = {
        "Results": [
            {"Variable": "Make", "Value": "TESLA"},
            {"Variable": "Model", "Value": "Model 3"},
            {"Variable": "Model Year", "Value": "2022"},
            {"Variable": "Plant Country", "Value": "UNITED STATES (USA)"},
        ]
    }
    client = GovAPIClient()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.json.return_value = mock_payload
        mock_resp.raise_for_status = AsyncMock()
        mock_get.return_value = mock_resp

        data = await client.decode_vin("5YJ3E1EB8NF123456")
        assert data.get("Make") == "TESLA"
        assert data.get("Model") == "Model 3"
        assert data.get("Model Year") == "2022"


@pytest.mark.asyncio
async def test_recalls_parsing():
    mock_payload = {
        "results": [
            {
                "NHTSACampaignNumber": "23V838000",
                "Component": "FORWARD COLLISION AVOIDANCE",
                "Summary": "Autosteer software may be insufficient.",
                "Conequence": "Increased risk of collision.",
                "Remedy": "Over-the-air (OTA) software update.",
                "ReportReceivedDate": "12/12/2023",
            }
        ]
    }
    client = GovAPIClient()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.json.return_value = mock_payload
        mock_resp.raise_for_status = AsyncMock()
        mock_get.return_value = mock_resp

        recalls = await client.get_recalls("Tesla", "Model 3", 2022)
        assert len(recalls) == 1
        assert recalls[0].campaign_number == "23V838000"
        assert "Autosteer" in recalls[0].summary

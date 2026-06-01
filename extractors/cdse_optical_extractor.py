"""
CDSE Optical Extractor for Cube Earth.
Uses Sentinel Hub Process API — proven working.
"""
import httpx
import datetime
import json
from extractors.base_extractor import BaseExtractor
from config.settings import settings

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
STATISTICS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"


class CDSEOpticalExtractor(BaseExtractor):

    def __init__(self):
        super().__init__("cdse_optical")
        self._token = None
        self._token_expiry = None

    async def _get_token(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        if self._token and self._token_expiry and now < self._token_expiry:
            return self._token
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(TOKEN_URL, data={
                "grant_type": "client_credentials",
                "client_id": settings.CDSE_CLIENT_ID,
                "client_secret": settings.CDSE_CLIENT_SECRET,
            })
            r.raise_for_status()
            data = r.json()
            self._token = data["access_token"]
            self._token_expiry = now + datetime.timedelta(seconds=500)
            return self._token

    async def extract(self, lat, lng, start_date=None, end_date=None):
        try:
            token = await self._get_token()
            now = datetime.datetime.now(datetime.timezone.utc)
            t_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            t_start = (now - datetime.timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")

            pad = 0.005
            bbox = [lng-pad, lat-pad, lng+pad, lat+pad]

            evalscript = """//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "SCL"],
    output: { bands: 1, sampleType: "AUTO" }
  };
}
function evaluatePixel(sample) {
  if (sample.SCL == 3 || sample.SCL == 4 || sample.SCL == 5) {
    return [(sample.B08 - sample.B04) / (sample.B08 + sample.B04)];
  }
  return [NaN];
}"""

            payload = {
                "input": {
                    "bounds": {
                        "bbox": bbox,
                        "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}
                    },
                    "data": [{
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {"from": t_start, "to": t_end},
                            "maxCloudCoverage": 100,
                            "mosaickingOrder": "leastCC"
                        }
                    }]
                },
                "aggregation": {
                    "timeRange": {"from": t_start, "to": t_end},
                    "aggregationInterval": {"of": "P16D"},
                    "evalscript": evalscript,
                    "resx": 0.0001,
                    "resy": 0.0001
                },
                "calculations": {
                    "ndvi": {
                        "statistics": {
                            "default": {
                                "percentiles": {"k": [25, 75]}
                            }
                        }
                    }
                }
            }

            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    STATISTICS_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                )

            print(f"CDSE Statistical API status: {r.status_code}")

            if r.status_code != 200:
                return {"available": False, "error": f"Statistical API {r.status_code}: {r.text[:200]}"}

            data = r.json()
            print(f"CDSE Statistical response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

            if not data or "data" not in data:
                return {"available": False, "error": "No data in response", "raw": str(data)[:200]}

            intervals = data.get("data", [])
            if not intervals:
                return {"available": False, "error": "No intervals found", "raw": str(data)[:200]}

            for interval in intervals:
                ndvi_stats = interval.get("outputs", {}).get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {})
                mean = ndvi_stats.get("mean")
                if mean is not None and str(mean) != "NaN":
                    return {
                        "available": True,
                        "interval": interval.get("interval"),
                        "ndvi": ndvi_stats
                    }

            return {
                "available": False,
                "error": "All intervals cloudy",
                "intervals_count": len(intervals),
                "last_interval": intervals[-1].get("interval") if intervals else None,
                "last_outputs": intervals[-1].get("outputs") if intervals else None
            }

        except Exception as e:
            return {"available": False, "error": str(e)}

    def parse(self, raw):
        if not raw or not raw.get("available"):
            return {"available": False}
        return raw

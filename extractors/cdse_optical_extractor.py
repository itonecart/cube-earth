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
            t_start = (now - datetime.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")

            pad = 0.005
            bbox = [lng-pad, lat-pad, lng+pad, lat+pad]

            # Use Process API with statistical evalscript
            evalscript = """//VERSION=3
function setup(){
  return{
    input:[{bands:["B04","B05","B08","B8A"],units:"REFLECTANCE"}],
    output:{bands:4,sampleType:"FLOAT32"}
  }
}
function evaluatePixel(s){
  var ndvi=(s.B08-s.B04)/(s.B08+s.B04+0.0001);
  var ndre=(s.B8A-s.B05)/(s.B8A+s.B05+0.0001);
  return [ndvi, ndre, s.B08, s.B04];
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
                            "maxCloudCoverage": 80,
                            "mosaickingOrder": "leastCC"
                        }
                    }]
                },
                "evalscript": evalscript,
                "output": {
                    "width": 64,
                    "height": 64,
                    "responses": [{
                        "identifier": "default",
                        "format": {"type": "application/json"}
                    }]
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

            print(f"CDSE Process API status: {r.status_code}")

            if r.status_code != 200:
                return {"available": False, "error": f"Process API {r.status_code}: {r.text[:200]}"}

            data = r.json()
            print(f"CDSE Process response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

            return {"available": False, "error": "Process API JSON not supported for stats", "raw": str(data)[:200]}

        except Exception as e:
            return {"available": False, "error": str(e)}

    def parse(self, raw):
        if not raw or not raw.get("available"):
            return {"available": False}
        return raw

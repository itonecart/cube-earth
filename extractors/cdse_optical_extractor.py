"""
CDSE Optical Extractor for Cube Earth.
Replaces GEE optical — uses Copernicus Data Space Sentinel Hub Process + Statistics API.
Free, no commercial license required.
"""
import httpx
import datetime
from extractors.base_extractor import BaseExtractor
from config.settings import settings

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"


class CDSEOpticalExtractor(BaseExtractor):

    def __init__(self):
        super().__init__("cdse_optical")
        self._token = None
        self._token_expiry = None

    async def _get_token(self):
        now = datetime.datetime.utcnow()
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
            self._token_expiry = now + datetime.timedelta(seconds=data.get("expires_in", 600) - 60)
            return self._token

    def _bbox(self, lat, lng, metres=150):
        import math
        dlat = metres / 111320
        dlng = metres / (111320 * math.cos(math.radians(lat)))
        return [lng - dlng, lat - dlat, lng + dlng, lat + dlat]

    async def extract(self, lat, lng, start_date=None, end_date=None):
        try:
            token = await self._get_token()
            now = datetime.datetime.utcnow()
            t_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            t_start = (now - datetime.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
            bbox = self._bbox(lat, lng, 150)

            evalscript = """//VERSION=3
function setup(){
  return{
    input:[{bands:["B04","B08"]}],
    output:[
      {id:"ndvi",bands:1,sampleType:"FLOAT32"},
      {id:"dataMask",bands:1}
    ]
  }
}
function evaluatePixel(s){
  const ndvi=(s.B08[0]-s.B04[0])/(s.B08[0]+s.B04[0]+1e-9);
  return{
    ndvi:[ndvi],
    dataMask:[1]
  }
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
                            "maxCloudCoverage": 80
                        }
                    }]
                },
                "aggregation": {
                    "timeRange": {"from": t_start, "to": t_end},
                    "aggregationInterval": {"of": "P1D"},
                    "evalscript": evalscript,
                    "width": 64,
                    "height": 64
                },
                "calculations": {
                    "ndvi": {
                        "statistics": {
                            "default": {
                                "percentiles": {"k": [25, 75]}
                            }
                        }
                    },
                    "ndre": {
                        "statistics": {
                            "default": {}
                        }
                    }
                }
            }

            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    STATS_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                )
                data = r.json()

            intervals = data.get("data", [])
            if not intervals:
                return {"available": False, "error": "No data returned"}

            # Find latest non-NaN interval
            latest = None
            for interval in reversed(intervals):
                ndvi_mean = interval.get("outputs", {}).get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {}).get("mean")
                if ndvi_mean and str(ndvi_mean) != "NaN":
                    latest = interval
                    break

            if not latest:
                return {"available": False, "error": "All intervals cloudy"}

            ndvi_stats = latest["outputs"]["ndvi"]["bands"]["B0"]["stats"]
            ndre_stats = latest["outputs"]["ndre"]["bands"]["B0"]["stats"]
            img_date = latest["interval"]["from"][:10]

            ndvi = ndvi_stats.get("mean")
            ndre = ndre_stats.get("mean")
            ndvi_std = ndvi_stats.get("stDev")
            ndvi_p25 = ndvi_stats.get("percentiles", {}).get("25.0")
            ndvi_p75 = ndvi_stats.get("percentiles", {}).get("75.0")

            if not ndvi or str(ndvi) == "NaN":
                return {"available": False, "error": "NaN NDVI"}

            # Calculate indices
            ndvi = round(float(ndvi), 4)
            ndre = round(float(ndre), 4) if ndre and str(ndre) != "NaN" else None
            cire = round(((ndre + 1) / (ndvi + 1e-9)) - 1, 4) if ndre else None
            gcap = round(ndvi * cire if cire and ndvi > 0.3 else 0.0, 4)

            # Uniformity
            uniformity = round(max(0, 10 - (float(ndvi_std) * 40)), 1) if ndvi_std and str(ndvi_std) != "NaN" else None

            # Age
            img_dt = datetime.datetime.strptime(img_date, "%Y-%m-%d")
            age_days = (datetime.datetime.utcnow() - img_dt).days

            return {
                "available": True,
                "ndvi": ndvi,
                "ndre": ndre,
                "cire": cire,
                "gcap": gcap,
                "ndvi_std": round(float(ndvi_std), 4) if ndvi_std and str(ndvi_std) != "NaN" else None,
                "ndvi_p25": round(float(ndvi_p25), 4) if ndvi_p25 and str(ndvi_p25) != "NaN" else None,
                "ndvi_p75": round(float(ndvi_p75), 4) if ndvi_p75 and str(ndvi_p75) != "NaN" else None,
                "uniformity": uniformity,
                "quad_ndvi": None,
                "date": img_date,
                "age_days": age_days,
                "source": "Copernicus CDSE Sentinel-2 L2A 10m",
                "cloud_cover": 0,
            }

        except Exception as e:
            return {"available": False, "error": str(e)}

    def parse(self, raw):
        if not raw or not raw.get("available"):
            return {"available": False}
        return raw

"""
CDSE Optical Extractor — uses Statistical API with working format.
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
            self._token = r.json()["access_token"]
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

            evalscript = """//VERSION=3
function setup(){
  return{
    input:[{bands:["B04","B08"]}],
    output:[
      {id:"ndvi",bands:1,sampleType:"AUTO"},
      {id:"dataMask",bands:1}
    ]
  }
}
function evaluatePixel(s){
  return{
    ndvi:[(s.B08[0]-s.B04[0])/(s.B08[0]+s.B04[0]+0.0001)],
    dataMask:[s.B08[0]>0?1:0]
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
                            "maxCloudCoverage": 80,
                            "mosaickingOrder": "leastCC"
                        }
                    }]
                },
                "aggregation": {
                    "timeRange": {"from": t_start, "to": t_end},
                    "aggregationInterval": {"of": "P16D"},
                    "evalscript": evalscript,
                    "width": 100,
                    "height": 100
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
                    STATS_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                )

            if r.status_code != 200:
                return {"available": False, "error": f"Stats API {r.status_code}: {r.text[:200]}"}

            data = r.json()
            intervals = data.get("data", [])

            # Find latest non-NaN interval
            for interval in reversed(intervals):
                stats = interval.get("outputs", {}).get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {})
                mean = stats.get("mean")
                if mean is not None and str(mean) != "NaN":
                    ndvi = round(float(mean), 4)
                    ndvi_std = float(stats.get("stDev", 0) or 0)
                    ndvi_p25 = float(stats.get("percentiles", {}).get("25.0", 0) or 0)
                    ndvi_p75 = float(stats.get("percentiles", {}).get("75.0", 0) or 0)
                    uniformity = round(max(0, 10 - (ndvi_std * 40)), 1)
                    img_date = interval.get("interval", {}).get("from", "")[:10]
                    img_dt = datetime.datetime.strptime(img_date, "%Y-%m-%d") if img_date else now.replace(tzinfo=None)
                    age_days = (now.replace(tzinfo=None) - img_dt).days

                    return {
                        "available": True,
                        "ndvi": ndvi,
                        "ndre": None,
                        "cire": None,
                        "gcap": None,
                        "ndvi_std": round(ndvi_std, 4),
                        "ndvi_p25": round(ndvi_p25, 4),
                        "ndvi_p75": round(ndvi_p75, 4),
                        "uniformity": uniformity,
                        "quad_ndvi": None,
                        "date": img_date,
                        "age_days": age_days,
                        "source": "Copernicus CDSE Sentinel-2 L2A 10m",
                        "cloud_cover": 0,
                    }

            return {
                "available": False,
                "error": "All intervals cloudy",
                "count": len(intervals),
                "last": intervals[-1].get("outputs") if intervals else None
            }

        except Exception as e:
            return {"available": False, "error": str(e)}

    def parse(self, raw):
        if not raw or not raw.get("available"):
            return {"available": False}
        return raw

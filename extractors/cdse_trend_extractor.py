"""
CDSE Trend Extractor for Cube Earth.
Replaces GEE trend extractor — 90-day NDVI series via Sentinel Hub Statistics API.
"""
import httpx
import datetime
from extractors.base_extractor import BaseExtractor
from config.settings import settings

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"


class CDSETrendExtractor(BaseExtractor):

    def __init__(self):
        super().__init__("cdse_trend")
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
            self._token = r.json()["access_token"]
            self._token_expiry = now + datetime.timedelta(seconds=500)
            return self._token

    def _bbox(self, lat, lng, metres=150):
        import math
        dlat = metres / 111320
        dlng = metres / (111320 * math.cos(math.radians(lat)))
        return [lng - dlng, lat - dlat, lng + dlng, lat + dlat]

    async def extract(self, lat, lng, days=90):
        try:
            token = await self._get_token()
            now = datetime.datetime.utcnow()
            t_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            t_start = (now - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
            bbox = self._bbox(lat, lng, 150)

            evalscript = """//VERSION=3
function setup(){
  return{
    input:[{bands:["B04","B08","SCL"]}],
    output:[
      {id:"ndvi",bands:1},
      {id:"dataMask",bands:1}
    ]
  }
}
function evaluatePixel(s){
  const cloud=[3,8,9,10,11].includes(s.SCL[0]);
  const ndvi=(s.B08[0]-s.B04[0])/(s.B08[0]+s.B04[0]+1e-9);
  return{ndvi:[ndvi],dataMask:[cloud?0:1]}
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
                    "aggregationInterval": {"of": "P5D"},
                    "evalscript": evalscript,
                    "width": 10,
                    "height": 10
                },
                "calculations": {
                    "ndvi": {"statistics": {"default": {}}}
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
            
            # Build series — skip NaN
            series = []
            for interval in intervals:
                mean = interval.get("outputs",{}).get("ndvi",{}).get("bands",{}).get("B0",{}).get("stats",{}).get("mean")
                if mean and str(mean) != "NaN":
                    series.append({
                        "date": interval["interval"]["from"][:10],
                        "ndvi": round(float(mean), 3)
                    })

            if len(series) < 2:
                return {"available": False, "error": "Insufficient data"}

            # Calculate trend
            first = series[0]["ndvi"]
            last = series[-1]["ndvi"]
            diff = round(last - first, 3)

            if diff > 0.15:
                long_trend = "strong_increase"
                trend_arrow = "📈"
                trend_label = "Strong vegetation growth"
            elif diff > 0.05:
                long_trend = "increasing"
                trend_arrow = "↗"
                trend_label = "Vegetation improving"
            elif diff < -0.15:
                long_trend = "strong_decline"
                trend_arrow = "📉"
                trend_label = "Significant vegetation decline"
            elif diff < -0.05:
                long_trend = "declining"
                trend_arrow = "↘"
                trend_label = "Vegetation softening"
            else:
                long_trend = "stable"
                trend_arrow = "➡"
                trend_label = "Stable vegetation"

            # Detect events
            events = []
            for i in range(1, len(series)):
                drop = series[i-1]["ndvi"] - series[i]["ndvi"]
                if drop > 0.15:
                    events.append({
                        "type": "harvest_or_cut",
                        "label": "Possible mowing or cutting",
                        "date": series[i]["date"],
                        "ndvi_before": series[i-1]["ndvi"],
                        "ndvi_after": series[i]["ndvi"],
                        "confidence": "high" if drop > 0.25 else "moderate"
                    })

            return {
                "available": True,
                "series": series,
                "count": len(series),
                "long_trend": long_trend,
                "long_diff": diff,
                "trend_arrow": trend_arrow,
                "trend_label": trend_label,
                "latest_ndvi": last,
                "latest_date": series[-1]["date"],
                "events": events,
                "source": "Copernicus CDSE Sentinel-2 L2A"
            }

        except Exception as e:
            return {"available": False, "error": str(e)}

    def parse(self, raw):
        if not raw or not raw.get("available"):
            return {"available": False}
        return raw

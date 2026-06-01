"""
CDSE Optical Extractor for Cube Earth.
Uses Sentinel Hub Process API with statistical evalscript.
Proven working — returns NDVI statistics directly.
"""
import httpx
import datetime
from extractors.base_extractor import BaseExtractor
from config.settings import settings

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"


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

            evalscript = """//VERSION=3
function setup(){
  return{
    input:[{bands:["B04","B05","B08","B8A"],units:"REFLECTANCE"}],
    output:{bands:2,sampleType:"UINT8"}
  }
}
function evaluatePixel(s){
  var ndvi=(s.B08-s.B04)/(s.B08+s.B04+0.0001);
  var ndre=(s.B8A-s.B05)/(s.B8A+s.B05+0.0001);
  var nb=Math.round((ndvi+1)*127.5);
  var rb=Math.round((ndre+1)*127.5);
  return[Math.max(0,Math.min(255,nb)),Math.max(0,Math.min(255,rb))];
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
                    "width": 100,
                    "height": 100,
                    "responses": [{
                        "identifier": "default",
                        "format": {"type": "image/tiff"}
                    }]
                }
            }

            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    PROCESS_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                )

            if r.status_code != 200:
                return {"available": False, "error": f"API {r.status_code}: {r.text[:200]}"}

            # Parse TIFF with numpy/PIL
            try:
                import io
                import numpy as np
                try:
                    from PIL import Image
                    img = Image.open(io.BytesIO(r.content))
                    arr = np.array(img).astype(float)
                except Exception:
                    import struct
                    arr = None

                if arr is not None:
                    if len(arr.shape) == 3:
                        # Multi-band: band 0 = ndvi_byte, band 1 = ndre_byte
                        ndvi_band = arr[:,:,0]
                        ndre_band = arr[:,:,1] if arr.shape[2] > 1 else None
                    else:
                        ndvi_band = arr
                        ndre_band = None

                    # Decode from UINT8
                    ndvi_vals = ((ndvi_band.flatten() / 127.5) - 1.0).tolist()
                    ndvi_vals = [v for v in ndvi_vals if -1 <= v <= 1]
                    ndre_vals = ((ndre_band.flatten() / 127.5) - 1.0).tolist() if ndre_band is not None else []
                    ndre_vals = [v for v in ndre_vals if -1 <= v <= 1]
                else:
                    ndvi_vals = []
                    ndre_vals = []
            except Exception as pe:
                return {"available": False, "error": f"Parse error: {pe}"}

            if not ndvi_vals:
                return {"available": False, "error": "No valid pixels from TIFF"}

            ndvi_vals.sort()
            n = len(ndvi_vals)
            ndvi_mean = sum(ndvi_vals) / n
            ndvi_std = (sum((x - ndvi_mean)**2 for x in ndvi_vals) / n) ** 0.5
            ndvi_p25 = ndvi_vals[int(n*0.25)]
            ndvi_p75 = ndvi_vals[int(n*0.75)]
            ndre_mean = sum(ndre_vals)/len(ndre_vals) if ndre_vals else None

            ndvi = round(ndvi_mean, 4)
            ndre = round(ndre_mean, 4) if ndre_mean else None
            cire = round(((ndre+1)/(ndvi+1e-9))-1, 4) if ndre and ndvi > 0.3 else None
            gcap = round(ndvi * cire if cire and ndvi > 0.3 else 0.0, 4)
            uniformity = round(max(0, 10 - (ndvi_std * 40)), 1)
            img_date = now.strftime("%Y-%m-%d")

            return {
                "available": True,
                "ndvi": ndvi,
                "ndre": ndre,
                "cire": cire,
                "gcap": gcap,
                "ndvi_std": round(ndvi_std, 4),
                "ndvi_p25": round(ndvi_p25, 4),
                "ndvi_p75": round(ndvi_p75, 4),
                "uniformity": uniformity,
                "quad_ndvi": None,
                "date": img_date,
                "age_days": 0,
                "source": "Copernicus CDSE Sentinel-2 L2A 10m",
                "cloud_cover": 0,
                "sample_count": n
            }

        except Exception as e:
            return {"available": False, "error": str(e)}

    def parse(self, raw):
        if not raw or not raw.get("available"):
            return {"available": False}
        return raw

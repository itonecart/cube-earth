"""
Sentinel-3 OLCI L2 Extractor
Uses CDSE Process API to get OGVI (vegetation index) and OTCI (chlorophyll)
300m resolution, 2-day revisit
"""
import datetime
import numpy as np
import os

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

class Sentinel3Extractor:
    def __init__(self):
        self._token = None
        self._token_expiry = None

    async def _get_token(self):
        import aiohttp, datetime
        now = datetime.datetime.utcnow()
        if self._token and self._token_expiry and now < self._token_expiry:
            return self._token
        async with aiohttp.ClientSession() as session:
            data = {
                "grant_type": "client_credentials",
                "client_id": os.environ.get("CDSE_CLIENT_ID", ""),
                "client_secret": os.environ.get("CDSE_CLIENT_SECRET", "")
            }
            async with session.post(TOKEN_URL, data=data) as r:
                resp = await r.json()
                self._token = resp.get("access_token")
                self._token_expiry = now + datetime.timedelta(seconds=500)
                return self._token

    async def get_ogvi(self, lat, lng, days_back=10):
        """
        Get OLCI Global Vegetation Index (OGVI) — similar to NDVI
        and OTCI (Terrestrial Chlorophyll Index)
        300m resolution, 2-day revisit
        """
        import aiohttp
        try:
            token = await self._get_token()
            if not token:
                return {"available": False, "error": "No token"}

            today = datetime.datetime.utcnow()
            date_from = (today - datetime.timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
            date_to = today.strftime("%Y-%m-%dT23:59:59Z")

            # Bounding box around point (300m buffer)
            pad = 0.005  # ~500m
            bbox = [lng-pad, lat-pad, lng+pad, lat+pad]

            payload = {
                "input": {
                    "bounds": {"bbox": bbox},
                    "data": [{
                        "type": "sentinel-3-olci-l2",
                        "dataFilter": {
                            "timeRange": {
                                "from": date_from,
                                "to": date_to
                            },
                            "maxCloudCoverage": 50
                        }
                    }]
                },
                "output": {
                    "width": 5,
                    "height": 5,
                    "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]
                },
                "evalscript": """//VERSION=3
function setup() {
  return {
    input: [{bands: ["OGVI", "OTCI", "dataMask"]}],
    output: {bands: 3, sampleType: "FLOAT32"}
  };
}
function evaluatePixel(s) {
  if (s.dataMask === 0) return [-9999, -9999, 0];
  return [s.OGVI, s.OTCI, s.dataMask];
}"""
            }

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
                async with session.post(PROCESS_URL, json=payload, headers=headers) as r:
                    if r.status != 200:
                        error = await r.text()
                        return {"available": False, "error": f"HTTP {r.status}: {error[:200]}"}

                    # Parse tiff response
                    import io
                    content = await r.read()
                    
                    try:
                        import tifffile
                        arr = tifffile.imread(io.BytesIO(content))
                    except:
                        return {"available": False, "error": "Could not parse TIFF"}

                    # arr shape: (height, width, bands) or (bands, height, width)
                    if arr.ndim == 3:
                        if arr.shape[0] == 3:
                            ogvi_band = arr[0]
                            otci_band = arr[1]
                            mask_band = arr[2]
                        else:
                            ogvi_band = arr[:,:,0]
                            otci_band = arr[:,:,1]
                            mask_band = arr[:,:,2]
                    else:
                        return {"available": False, "error": "Unexpected array shape"}

                    # Filter valid pixels
                    valid = (mask_band > 0) & (ogvi_band > -9000) & (ogvi_band >= 0) & (ogvi_band <= 1)
                    
                    if not np.any(valid):
                        return {"available": False, "error": "No valid pixels"}

                    ogvi_mean = float(np.mean(ogvi_band[valid]))
                    otci_mean = float(np.mean(otci_band[valid])) if np.any(valid) else None

                    return {
                        "available": True,
                        "ogvi": round(ogvi_mean, 4),
                        "otci": round(otci_mean, 4) if otci_mean else None,
                        "pixel_count": int(np.sum(valid)),
                        "date_from": date_from,
                        "date_to": date_to,
                        "note": "OGVI: OLCI Global Vegetation Index (300m, 2-day revisit)"
                    }

        except Exception as e:
            return {"available": False, "error": str(e)}

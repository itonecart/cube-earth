"""
GEE Optical Extractor for Cube Earth.
Replaces HLS for current NDVI — always fresh 10m Sentinel-2 data.
"""
import datetime
from extractors.base_extractor import BaseExtractor


class GEEOpticalExtractor(BaseExtractor):

    def __init__(self, project='ireland-mrv-prototype'):
        super().__init__("gee_optical")
        self.project = project
        self._initialized = False

    def _ensure_init(self):
        if not self._initialized:
            try:
                import ee
                ee.Initialize(project=self.project)
                self._initialized = True
            except Exception:
                try:
                    import os, json, ee
                    creds_json = os.getenv("GEE_CREDENTIALS")
                    if creds_json:
                        creds_path = os.path.expanduser("~/.config/earthengine/credentials")
                        os.makedirs(os.path.dirname(creds_path), exist_ok=True)
                        with open(creds_path, "w") as f:
                            json.dump(json.loads(creds_json), f)
                    ee.Initialize(project=self.project)
                    self._initialized = True
                except Exception as e:
                    print(f"GEE optical init failed: {e}")
        return self._initialized

    async def extract(self, lat, lng, start_date=None, end_date=None):
        if not self._ensure_init():
            return {"available": False, "error": "GEE not initialized"}

        try:
            import ee

            point = ee.Geometry.Point([lng, lat])
            buffer = point.buffer(150)

            # Last 60 days — find most recent clear image
            end = datetime.datetime.utcnow()
            start = end - datetime.timedelta(days=60)

            s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(buffer)
                  .filterDate(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
                  .sort('system:time_start', False))

            count = s2.size().getInfo()
            if count == 0:
                # Try with higher cloud tolerance
                s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                      .filterBounds(buffer)
                      .filterDate(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))
                      .sort('system:time_start', False))
                count = s2.size().getInfo()

            if count == 0:
                return {"available": False, "error": "No cloud-free S2 imagery"}

            latest = s2.first()
            date_ms = latest.date().millis().getInfo()
            image_date = datetime.datetime.fromtimestamp(
                date_ms / 1000, tz=datetime.timezone.utc
            ).strftime('%Y-%m-%d')

            # Extract bands
            bands = latest.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=buffer,
                scale=10
            ).getInfo()

            b4  = bands.get('B4', 0) or 0    # Red
            b8  = bands.get('B8', 0) or 0    # NIR
            b5  = bands.get('B5', 0) or 0    # Red Edge 1
            b6  = bands.get('B6', 0) or 0    # Red Edge 2
            b7  = bands.get('B7', 0) or 0    # Red Edge 3
            b11 = bands.get('B11', 0) or 0   # SWIR1
            b2  = bands.get('B2', 0) or 0    # Blue

            # Scale from DN to reflectance (S2 SR is already scaled)
            # Values are 0-10000 in GEE for SR harmonized
            scale = 10000.0

            r4  = b4  / scale
            r8  = b8  / scale
            r5  = b5  / scale
            r6  = b6  / scale
            r7  = b7  / scale
            r11 = b11 / scale

            # NDVI
            ndvi = (r8 - r4) / (r8 + r4 + 1e-9)

            # NDRE (Red Edge NDVI) — B7 and B5
            ndre = (r7 - r5) / (r7 + r5 + 1e-9)

            # CIre (Chlorophyll Index Red Edge)
            cire = (r7 / (r5 + 1e-9)) - 1

            # GCAP (Grassland Carbon Accumulation Proxy)
            gcap = ndvi * cire if ndvi > 0.3 else 0.0

            # Cloud cover
            cloud_pct = latest.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()

            age_days = (datetime.datetime.utcnow() - 
                       datetime.datetime.strptime(image_date, '%Y-%m-%d')).days

            return {
                "available":    True,
                "date":         image_date,
                "age_days":     age_days,
                "ndvi":         round(ndvi, 4),
                "ndre":         round(ndre, 4),
                "cire":         round(cire, 4),
                "gcap":         round(gcap, 4),
                "cloud_cover":  round(cloud_pct, 1),
                "source":       "GEE Sentinel-2 SR 10m",
                "bands": {
                    "B4": round(r4, 4),
                    "B8": round(r8, 4),
                    "B5": round(r5, 4),
                    "B7": round(r7, 4),
                },
            }

        except Exception as e:
            return {"available": False, "error": str(e)}

    def parse(self, raw):
        if not raw or not raw.get("available"):
            return {"available": False, "source": "GEE Optical"}
        return raw

    def quality(self):
        return {
            "sensor":      "GEE Sentinel-2",
            "confidence":  "high",
            "resolution":  "10m",
            "limitations": ["Requires GEE auth"],
        }

import httpx
import math
from extractors.base_extractor import BaseExtractor


ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"


class NASADEMExtractor(BaseExtractor):

    def __init__(self):
        super().__init__("nasadem")

    async def extract(self, lat, lng, start_date=None, end_date=None):
        d = 0.001
        lats = ",".join(str(round(lat + o, 6)) for o in [0, d, -d, 0, 0])
        lngs = ",".join(str(round(lng + o, 6)) for o in [0, 0, 0, d, -d])
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                ELEVATION_URL,
                params={"latitude": lats, "longitude": lngs},
            )
            r.raise_for_status()
            return r.json()

    def parse(self, raw):
        if not raw:
            return {"available": False, "source": "NASADEM"}
        elev = raw.get("elevation", [])
        if len(elev) < 5:
            return {"available": False, "source": "NASADEM"}
        center, north, south, east, west = elev
        d_lat = 0.001 * 111320
        d_lng = 0.001 * 111320
        slope = math.degrees(math.atan(math.sqrt(
            ((east - west) / (2 * d_lng)) ** 2 +
            ((north - south) / (2 * d_lat)) ** 2
        )))
        if center > 1500:
            terrain = "mountainous"
        elif center > 500:
            terrain = "hilly"
        elif center > 120:
            terrain = "rolling"
        elif slope > 3:
            terrain = "undulating"
        else:
            terrain = "flat"
        return {
            "available":     True,
            "elevation_m":   round(center),
            "slope_deg":     round(slope, 2),
            "terrain":       terrain,
            "source":        "Open-Meteo elevation",
        }

    def quality(self):
        return {
            "sensor":      "nasadem",
            "confidence":  "high",
            "resolution":  "30m",
            "limitations": [
                "Slope estimated from 5-point finite difference",
            ],
        }

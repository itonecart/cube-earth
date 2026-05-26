import httpx
import math
from extractors.base_extractor import BaseExtractor

ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"

class NASADEMExtractor(BaseExtractor):

    def __init__(self):
        super().__init__("nasadem")

    async def extract(self, lat, lng, start_date=None, end_date=None):
        d = 0.001
        points = [
            (lat, lng),
            (lat + d, lng),
            (lat - d, lng),
            (lat, lng + d),
            (lat, lng - d),
        ]
        results = []
        async with httpx.AsyncClient(timeout=15) as client:
            for plat, plng in points:
                try:
                    r = await client.get(
                        ELEVATION_URL,
                        params={
                            "latitude": round(plat, 6),
                            "longitude": round(plng, 6),
                        },
                    )
                    r.raise_for_status()
                    data = r.json()
                    elev = data.get("elevation", [None])
                    results.append(elev[0] if elev else None)
                except Exception:
                    results.append(None)
        return {"elevation": results}

    def parse(self, raw):
        if not raw:
            return {"available": False, "source": "NASADEM"}
        elev = raw.get("elevation", [])
        if len(elev) < 5 or any(e is None for e in elev):
            # Fall back to center point only
            center = elev[0] if elev and elev[0] is not None else None
            if center is None:
                return {"available": False, "source": "NASADEM"}
            return {
                "available":   True,
                "elevation_m": round(center),
                "slope_deg":   0.0,
                "terrain":     "flat" if center < 120 else "rolling",
                "source":      "Open-Meteo elevation",
            }
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
            "available":   True,
            "elevation_m": round(center),
            "slope_deg":   round(slope, 2),
            "terrain":     terrain,
            "source":      "Open-Meteo elevation",
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

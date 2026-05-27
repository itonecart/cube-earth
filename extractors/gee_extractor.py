"""
Google Earth Engine extractor for Cube Earth.
Provides NDVI time series and trend calculation.
"""
import ee
import datetime
from extractors.base_extractor import BaseExtractor


def init_gee(project='ireland-mrv-prototype'):
    import os, json
    try:
        # Try env var first (Render production)
        creds_json = os.getenv("GEE_CREDENTIALS")
        if creds_json:
            import tempfile
            creds = json.loads(creds_json)
            creds_path = os.path.expanduser("~/.config/earthengine/credentials")
            os.makedirs(os.path.dirname(creds_path), exist_ok=True)
            with open(creds_path, "w") as f:
                json.dump(creds, f)
        ee.Initialize(project=project)
        return True
    except Exception as e:
        print(f"GEE init failed: {e}")
        return False


class GEEExtractor(BaseExtractor):

    def __init__(self, project='ireland-mrv-prototype'):
        super().__init__("gee")
        self.project = project
        self._initialized = False

    def _ensure_init(self):
        if not self._initialized:
            self._initialized = init_gee(self.project)
        return self._initialized

    async def extract(self, lat, lng, start_date=None, end_date=None):
        if not self._ensure_init():
            return {"available": False, "error": "GEE not initialized"}

        try:
            point = ee.Geometry.Point([lng, lat])

            # Get last 90 days of S2
            end = datetime.datetime.utcnow()
            start = end - datetime.timedelta(days=90)

            s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(point)
                  .filterDate(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
                  .sort('system:time_start', False)
                  .limit(10))

            count = s2.size().getInfo()
            if count == 0:
                return {"available": False, "error": "No GEE images found"}

            def get_ndvi(img):
                ndvi = img.normalizedDifference(['B8', 'B4'])
                val = ndvi.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=point.buffer(100),
                    scale=10
                )
                return img.set('ndvi', val.get('nd'))

            results = s2.map(get_ndvi)
            ndvi_list = results.aggregate_array('ndvi').getInfo()
            date_list = results.aggregate_array('system:time_start').getInfo()

            # Build time series
            series = []
            for d, n in zip(date_list, ndvi_list):
                if n is not None:
                    date_str = datetime.datetime.fromtimestamp(
                        d/1000, tz=datetime.timezone.utc
                    ).strftime('%Y-%m-%d')
                    series.append({"date": date_str, "ndvi": round(n, 4)})

            # Sort by date ascending
            series.sort(key=lambda x: x["date"])

            return {
                "available": True,
                "series": series,
                "count": len(series),
                "source": "GEE Sentinel-2 SR Harmonized",
            }

        except Exception as e:
            return {"available": False, "error": str(e)}

    def parse(self, raw):
        if not raw or not raw.get("available"):
            return {"available": False, "source": "GEE"}

        series = raw.get("series", [])
        if len(series) < 2:
            return {
                "available": True,
                "series": series,
                "trend": "insufficient_data",
                "trend_label": "Insufficient data for trend",
                "source": raw.get("source"),
            }

        # Latest and previous NDVI
        latest = series[-1]
        previous = series[-2] if len(series) >= 2 else None
        oldest = series[0]

        # Short term trend (last 2 observations)
        short_diff = None
        short_trend = "stable"
        if previous:
            short_diff = round(latest["ndvi"] - previous["ndvi"], 4)
            if short_diff > 0.05:
                short_trend = "increasing"
            elif short_diff < -0.05:
                short_trend = "declining"
            else:
                short_trend = "stable"

        # Long term trend (first vs last)
        long_diff = round(latest["ndvi"] - oldest["ndvi"], 4)
        if long_diff > 0.10:
            long_trend = "strong_increase"
        elif long_diff > 0.05:
            long_trend = "increasing"
        elif long_diff < -0.10:
            long_trend = "strong_decline"
        elif long_diff < -0.05:
            long_trend = "declining"
        else:
            long_trend = "stable"

        # Trend arrows
        arrows = {
            "increasing": "↑",
            "strong_increase": "↑↑",
            "declining": "↓",
            "strong_decline": "↓↓",
            "stable": "→",
        }

        trend_labels = {
            "increasing": "Increasing vegetation",
            "strong_increase": "Strong vegetation growth",
            "declining": "Declining vegetation",
            "strong_decline": "Strong vegetation decline",
            "stable": "Stable vegetation",
        }

        return {
            "available": True,
            "series": series,
            "latest": latest,
            "previous": previous,
            "oldest": oldest,
            "short_trend": short_trend,
            "long_trend": long_trend,
            "short_diff": short_diff,
            "long_diff": long_diff,
            "trend_arrow": arrows.get(long_trend, "→"),
            "trend_label": trend_labels.get(long_trend, "Stable"),
            "count": len(series),
            "source": raw.get("source"),
        }

    def quality(self):
        return {
            "sensor": "GEE Sentinel-2",
            "confidence": "high",
            "resolution": "10m",
            "limitations": ["Requires GEE authentication"],
        }

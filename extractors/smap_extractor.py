import httpx
from extractors.base_extractor import BaseExtractor
from catalog.earthdata_client import EarthdataClient
from config.settings import settings


class SMAPExtractor(BaseExtractor):

    def __init__(self):
        super().__init__("smap")
        self.client = EarthdataClient()
        self.collection = settings.SMAP_COLLECTION

    async def extract(self, lat, lng, start_date, end_date):
        granule = await self.client.latest_granule(
            self.collection,
            lat, lng,
            start_date, end_date,
        )
        if not granule:
            return None
        download_url = self.client.download_url(granule)
        if not download_url:
            return None
        return {
            "granule_id":    granule.get("id"),
            "granule_title": granule.get("title"),
            "download_url":  download_url,
            "time_start":    granule.get("time_start"),
            "time_end":      granule.get("time_end"),
        }

    def parse(self, raw):
        if not raw:
            return {
                "available": False,
                "source": "SMAP L4",
            }
        return {
            "available":     True,
            "granule_id":    raw.get("granule_id"),
            "download_url":  raw.get("download_url"),
            "time_start":    raw.get("time_start"),
            "source":        "SMAP L4 SPL4SMGP",
            "resolution":    "9km EASE-2",
            "collection":    self.collection,
        }

    def quality(self):
        return {
            "sensor":      "smap",
            "confidence":  "high",
            "resolution":  "9km",
            "limitations": [
                "Coarse resolution - not parcel precise",
                "4-hour latency for near-real-time",
            ],
        }

import httpx
from extractors.base_extractor import BaseExtractor
from config.settings import settings
from parsers.ecostress_parser import extract_lst

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"


class ECOSTRESSExtractor(BaseExtractor):

    def __init__(self):
        super().__init__("ecostress")
        self.collection = settings.ECOSTRESS_COLLECTION

    def _headers(self):
        return {
            "Authorization": f"Bearer {settings.NASA_TOKEN}",
            "Accept": "application/json",
        }

    def _parse_links(self, entry):
        links = {}
        for l in entry.get("links", []):
            href = l.get("href", "")
            if not href.startswith("https://"):
                continue
            if "lp-prod-protected" not in href:
                continue
            if href.endswith("_LST.tif"):
                links["lst"] = href
            elif href.endswith("_QC.tif"):
                links["qc"] = href
        return links

    async def _search(self, lat, lng, start_date, end_date, page_size=50):
        bbox = f"{lng-0.4},{lat-0.4},{lng+0.4},{lat+0.4}"
        params = {
            "collection_concept_id": self.collection,
            "temporal":   f"{start_date}T00:00:00Z,{end_date}T23:59:59Z",
            "bounding_box": bbox,
            "page_size":  page_size,
            "sort_key":   "-start_date",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                CMR_URL,
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
        return r.json().get("feed", {}).get("entry", [])

    async def extract(self, lat, lng, start_date, end_date):
        entries = await self._search(lat, lng, start_date, end_date, page_size=50)

        def score(e):
            from datetime import datetime, timezone
            t = e.get("time_start", "")
            month = int(t[5:7]) if len(t) >= 7 else 6
            age = 0
            try:
                dt  = datetime.fromisoformat(t.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - dt).days
            except Exception:
                pass
            return (1000 if 4 <= month <= 10 else 0) - age

        entries.sort(key=score, reverse=True)

        for entry in entries:
            links = self._parse_links(entry)
            if not links.get("lst"):
                continue
            granule = {
                "title":      entry.get("title"),
                "time_start": entry.get("time_start"),
                "links":      links,
            }
            result = await extract_lst(granule, lat, lng)
            if result.get("available"):
                return granule

        return None

    def parse(self, raw):
        if not raw:
            return {"available": False, "source": "ECOSTRESS"}
        return {
            "available":  True,
            "title":      raw.get("title"),
            "time_start": raw.get("time_start"),
            "links":      raw.get("links"),
            "source":     "ECOSTRESS ECO_L2T_LSTE V002 (70m)",
        }

    def quality(self):
        return {
            "sensor":      "ecostress",
            "confidence":  "high",
            "resolution":  "70m",
            "limitations": [
                "Cloud cover limits availability",
                "Ireland Atlantic cloud - 180 day search needed",
            ],
        }

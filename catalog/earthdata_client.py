from catalog.auth import EarthdataAuth
from catalog.http_client import HttpClient

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"


class EarthdataClient:

    def __init__(self):
        self.auth = EarthdataAuth()

    async def search_granules(
        self,
        collection_id,
        lat,
        lng,
        start_date,
        end_date,
        limit=10,
    ):
        bbox = (
            f"{lng-0.05},{lat-0.05},"
            f"{lng+0.05},{lat+0.05}"
        )
        params = {
            "collection_concept_id": collection_id,
            "temporal":              f"{start_date},{end_date}",
            "bounding_box":          bbox,
            "page_size":             limit,
            "sort_key":              "-start_date",
        }
        async with HttpClient() as client:
            data = await client.get(
                CMR_URL,
                headers=self.auth.headers(),
                params=params,
            )
        entries = data.get("feed", {}).get("entry", [])
        return entries

    async def latest_granule(
        self,
        collection_id,
        lat,
        lng,
        start_date,
        end_date,
    ):
        entries = await self.search_granules(
            collection_id,
            lat,
            lng,
            start_date,
            end_date,
            limit=1,
        )
        return entries[0] if entries else None

    def download_url(self, granule):
        links = granule.get("links", [])
        for link in links:
            href = link.get("href", "")
            if href.endswith(".h5") or href.endswith(".tif"):
                return href
        return None


earthdata = EarthdataClient()

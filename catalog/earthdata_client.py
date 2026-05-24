from catalog.auth import EarthdataAuth
from catalog.http_client import HttpClient


class EarthdataClient:

    def __init__(
        self,
        auth: EarthdataAuth
    ):

        self.auth = auth

        self.http = HttpClient()

        self.base = (
            "https://cmr.earthdata.nasa.gov"
        )

    async def collections(
        self,
        keyword=None
    ):

        url = (
            f"{self.base}"
            "/search/collections.json"
        )

        params = {

            "page_size": 25

        }

        if keyword:

            params[
                "keyword"
            ] = keyword

        response = await self.http.get(

            url,

            params=params

        )

        return response

    async def granules(
        self,
        collection,
        bbox,
        start_date,
        end_date,
        page_size=25
    ):

        url = (
            f"{self.base}"
            "/search/granules.json"
        )

        params = {

            "concept_id":
            collection,

            "bounding_box":
            bbox,

            "temporal":
            (
                f"{start_date}"
                "T00:00:00Z,"
                f"{end_date}"
                "T23:59:59Z"
            ),

            "page_size":
            page_size,

            "sort_key":
            "-start_date"

        }

        response = await self.http.get(

            url,

            params=params

        )

        return response

    async def metadata(
        self,
        granule_id
    ):

        url = (

            f"{self.base}"

            "/search/granules"

            f"/{granule_id}"

            ".json"

        )

        response = await self.http.get(

            url

        )

        return response

    async def collection_and_granules(

        self,

        keyword,

        bbox,

        start_date,

        end_date

    ):

        collections = await self.collections(

            keyword

        )

        feed = collections.get(

            "feed",

            {}

        )

        entries = feed.get(

            "entry",

            []

        )

        if not entries:

            return {

                "success": False,

                "reason":
                "collection_not_found"

            }

        collection = entries[0]

        concept_id = collection.get(

            "id"

        )

        granules = await self.granules(

            concept_id,

            bbox,

            start_date,

            end_date

        )

        return {

            "success": True,

            "collection": collection,

            "granules": granules

        }

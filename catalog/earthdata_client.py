# Earthdata catalog client

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

        raise NotImplementedError

    async def granules(
        self,
        collection,
        bbox,
        start_date,
        end_date
    ):

        raise NotImplementedError

    async def metadata(
        self,
        granule_id
    ):

        raise NotImplementedError

# Earthdata catalog client

from catalog.auth import EarthdataAuth


class EarthdataClient:

    def __init__(
        self,
        auth: EarthdataAuth
    ):

        self.auth = auth

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

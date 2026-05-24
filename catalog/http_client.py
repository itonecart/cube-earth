# HTTP foundation

import aiohttp


class HttpClient:

    def __init__(self):

        self.timeout = 60

    async def get(
        self,
        url,
        headers=None,
        params=None
    ):

        raise NotImplementedError

    async def post(
        self,
        url,
        payload=None,
        headers=None
    ):

        raise NotImplementedError

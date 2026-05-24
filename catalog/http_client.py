import aiohttp


class HttpClient:

    def __init__(

        self,

        timeout=60

    ):

        self.timeout = timeout

    async def get(

        self,

        url,

        headers=None,

        params=None

    ):

        timeout = aiohttp.ClientTimeout(

            total=self.timeout

        )

        async with aiohttp.ClientSession(

            timeout=timeout

        ) as session:

            async with session.get(

                url,

                headers=headers,

                params=params

            ) as response:

                response.raise_for_status()

                return await response.json()

    async def post(

        self,

        url,

        payload=None,

        headers=None

    ):

        timeout = aiohttp.ClientTimeout(

            total=self.timeout

        )

        async with aiohttp.ClientSession(

            timeout=timeout

        ) as session:

            async with session.post(

                url,

                headers=headers,

                json=payload

            ) as response:

                response.raise_for_status()

                return await response.json()

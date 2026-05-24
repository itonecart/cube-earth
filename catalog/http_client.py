import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class HttpClient:

    def __init__(self, timeout=30):
        self.timeout = timeout
        self._client = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get(self, url, headers=None, params=None):
        r = await self._client.get(
            url,
            headers=headers or {},
            params=params or {},
        )
        r.raise_for_status()
        return r.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_bytes(self, url, headers=None, params=None):
        r = await self._client.get(
            url,
            headers=headers or {},
            params=params or {},
        )
        r.raise_for_status()
        return r.content

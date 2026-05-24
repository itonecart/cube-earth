import httpx
from config.settings import settings


class EarthdataAuth:

    def __init__(self):
        self.token = settings.NASA_TOKEN

    def headers(self):
        if not self.token:
            raise ValueError(
                "NASA_EARTHDATA_TOKEN not set in .env"
            )
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    async def validate(self):
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://urs.earthdata.nasa.gov/api/users/tokens",
                headers=self.headers(),
                timeout=10,
            )
            return r.status_code == 200


auth = EarthdataAuth()

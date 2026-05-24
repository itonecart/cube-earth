import httpx
from config.settings import settings


class LPISClient:

    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_KEY

    def _headers(self):
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }

    async def get_parcel(self, lat, lng):
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.url}/rest/v1/ireland_lpis",
                headers=self._headers(),
                params=[
                    ("centroid_lat", f"gte.{round(lat-0.05,4)}"),
                    ("centroid_lat", f"lte.{round(lat+0.05,4)}"),
                    ("centroid_lng", f"gte.{round(lng-0.05,4)}"),
                    ("centroid_lng", f"lte.{round(lng+0.05,4)}"),
                    ("select", "*"),
                    ("limit", "20"),
                ],
                timeout=10,
            )
            if not r.is_success:
                return None
            rows = r.json()
            if not rows:
                return None
            return min(
                rows,
                key=lambda p: (
                    abs(p["centroid_lat"] - lat) +
                    abs(p["centroid_lng"] - lng)
                )
            )

    async def get_commonage(self, lat, lng):
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.url}/rest/v1/rpc/terraq_commonage_lookup",
                headers={
                    **self._headers(),
                    "Content-Type": "application/json"
                },
                json={"p_lat": lat, "p_lng": lng},
                timeout=10,
            )
            if not r.is_success:
                return None
            rows = r.json()
            return rows[0] if rows else None


lpis = LPISClient()

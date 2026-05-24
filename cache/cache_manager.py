import json
import httpx
from datetime import datetime, timezone, timedelta
from config.settings import settings


class CacheManager:

    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_KEY

    def _headers(self):
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }

    async def get(self, table, cache_key):
        now = datetime.now(timezone.utc).isoformat()
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.url}/rest/v1/{table}",
                headers=self._headers(),
                params={
                    "cache_key": f"eq.{cache_key}",
                    "expires_at": f"gt.{now}",
                    "select": "payload",
                    "limit": "1",
                },
                timeout=5,
            )
            if not r.is_success:
                return None
            rows = r.json()
            return rows[0]["payload"] if rows else None

    async def set(self, table, cache_key, payload, ttl_seconds):
        expires = (
            datetime.now(timezone.utc)
            + timedelta(seconds=ttl_seconds)
        ).isoformat()
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.url}/rest/v1/{table}",
                headers=self._headers(),
                content=json.dumps({
                    "cache_key": cache_key,
                    "payload": payload,
                    "expires_at": expires,
                }),
                timeout=5,
            )

    async def get_parcel(self, lat, lng):
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.url}/rest/v1/ireland_lpis",
                headers=self._headers(),
                params={
                    "centroid_lat": f"gte.{lat-0.01}",
                    "centroid_lng": f"gte.{lng-0.01}",
                    "select": "*",
                    "limit": "1",
                },
                timeout=5,
            )
            if not r.is_success:
                return None
            rows = r.json()
            return rows[0] if rows else None


cache = CacheManager()

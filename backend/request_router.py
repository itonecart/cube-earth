from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.bootstrap import Bootstrap

app = FastAPI(title="Cube Earth API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

service = Bootstrap().build()


class ProfileRequest(BaseModel):
    lat:  float
    lng:  float
    year: int = 2026
    parcel_override: dict = None


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok", "service": "cube-earth"}


@app.get("/parcels_in_bbox")
async def parcels_in_bbox(minlng: float, minlat: float, maxlng: float, maxlat: float):
    import httpx
    url = f"https://geoapi.opendata.agriculture.gov.ie/shps/collections/anonymous-lpis-data-for-2024_2024-lpis-data/items?bbox={minlng},{minlat},{maxlng},{maxlat}&f=json&limit=50"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        return r.json()

@app.get("/parcel_at_point")
async def parcel_at_point(lat: float, lng: float):
    from parcel.dafm_api import get_parcel_at_point
    result = await get_parcel_at_point(lat, lng)
    if not result:
        return {"features": [], "error": "No parcel found"}
    return {"features": [{"properties": result}], "matched": True}

@app.post("/field_profile")
async def field_profile(req: ProfileRequest):
    try:
        result = await service.build_profile(req.lat, req.lng, req.year, parcel_override=req.parcel_override)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/wms_token")
async def wms_token():
    """Get short-lived token for Sentinel Hub WMS tiles."""
    import httpx
    from config.settings import settings
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.CDSE_CLIENT_ID,
                "client_secret": settings.CDSE_CLIENT_SECRET,
            }
        )
        data = r.json()
        token = data.get("access_token")
        return {
            "token": token,
            "wms_url": f"https://sh.dataspace.copernicus.eu/ogc/wms/TOKEN?token={token}"
        }

@app.get("/wms_tile")
async def wms_tile(
    layer: str = "TRUE-COLOR-S2L2A",
    bbox: str = "",
    width: int = 256,
    height: int = 256,
    time: str = "2026-05-01/2026-05-31"
):
    """Proxy Sentinel Hub WMS tiles with auth header."""
    import httpx
    from config.settings import settings
    
    # Get token
    async with httpx.AsyncClient(timeout=10) as client:
        token_r = await client.post(
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.CDSE_CLIENT_ID,
                "client_secret": settings.CDSE_CLIENT_SECRET,
            }
        )
        token = token_r.json().get("access_token")
        
        # Fetch WMS tile
        wms_url = (
            f"https://sh.dataspace.copernicus.eu/ogc/wms"
            f"?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap"
            f"&LAYERS={layer}"
            f"&BBOX={bbox}"
            f"&WIDTH={width}&HEIGHT={height}"
            f"&CRS=EPSG:3857"
            f"&FORMAT=image/jpeg"
            f"&TIME={time}"
            f"&MAXCC=80"
        )
        
        tile_r = await client.get(
            wms_url,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        from fastapi.responses import Response
        return Response(
            content=tile_r.content,
            media_type="image/jpeg"
        )

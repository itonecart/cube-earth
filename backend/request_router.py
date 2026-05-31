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
        result = await service.build(req.lat, req.lng, req.year, parcel_override=req.parcel_override)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

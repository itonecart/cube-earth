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
    minlng: float = -9.5,
    minlat: float = 52.0,
    maxlng: float = -9.4,
    maxlat: float = 52.1,
    time: str = "2026-05-01/2026-05-31"
):
    """Sentinel-2 true color via Process API."""
    import httpx
    from config.settings import settings
    from fastapi.responses import Response

    evalscript = """//VERSION=3
function setup(){return{input:["B04","B03","B02"],output:{bands:3,sampleType:"UINT8"}}}
function evaluatePixel(s){
  return [Math.min(255,s.B04*3.5*255),Math.min(255,s.B03*3.5*255),Math.min(255,s.B02*3.5*255)]
}"""

    async with httpx.AsyncClient(timeout=30) as client:
        token_r = await client.post(
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
            data={"grant_type":"client_credentials","client_id":settings.CDSE_CLIENT_ID,"client_secret":settings.CDSE_CLIENT_SECRET}
        )
        token = token_r.json().get("access_token")
        t0, t1 = time.split("/")
        process_r = await client.post(
            "https://sh.dataspace.copernicus.eu/api/v1/process",
            headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},
            json={
                "input":{
                    "bounds":{"bbox":[minlng,minlat,maxlng,maxlat],"properties":{"crs":"http://www.opengis.net/def/crs/EPSG/0/4326"}},
                    "data":[{"type":"sentinel-2-l2a","dataFilter":{"timeRange":{"from":f"{t0}T00:00:00Z","to":f"{t1}T23:59:59Z"},"maxCloudCoverage":80,"mosaickingOrder":"leastCC"}}]
                },
                "evalscript":evalscript,
                "output":{"width":1024,"height":1024,"responses":[{"identifier":"default","format":{"type":"image/jpeg"}}]}
            }
        )
        return Response(content=process_r.content,media_type="image/jpeg")



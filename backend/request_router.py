from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.bootstrap import Bootstrap
from extractors.weather_extractor import get_weather_data

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


@app.get("/zone_xyz/{z}/{x}/{y}.png")
async def zone_xyz(z: int, x: int, y: int):
    """XYZ tile endpoint for variability zones — compatible with L.tileLayer."""
    import httpx, io, numpy as np, math
    from PIL import Image
    from config.settings import settings
    from fastapi.responses import Response

    # Convert XYZ to bbox
    def tile_to_bbox(x, y, z):
        n = 2**z
        lon_min = x/n*360 - 180
        lon_max = (x+1)/n*360 - 180
        lat_max = math.degrees(math.atan(math.sinh(math.pi*(1-2*y/n))))
        lat_min = math.degrees(math.atan(math.sinh(math.pi*(1-2*(y+1)/n))))
        return lon_min, lat_min, lon_max, lat_max

    minlng, minlat, maxlng, maxlat = tile_to_bbox(x, y, z)

    # Only render for Ireland bbox
    if maxlng < -11 or minlng > -5 or maxlat < 51 or minlat > 56:
        # Return transparent tile
        img = Image.new('RGBA', (256,256), (0,0,0,0))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return Response(content=buf.getvalue(), media_type='image/png')

    evalscript = """//VERSION=3
function setup(){return{input:[{bands:["B04","B08"],units:"REFLECTANCE"}],output:{bands:1,sampleType:"UINT8"}}}
function evaluatePixel(s){var ndvi=(s.B08-s.B04)/(s.B08+s.B04+0.0001);return[Math.round((ndvi+1)*127.5)];}"""

    now = __import__('datetime').datetime.utcnow()
    t_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    t_start = (now - __import__('datetime').timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token_r = await client.post(
                "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
                data={"grant_type":"client_credentials","client_id":settings.CDSE_CLIENT_ID,"client_secret":settings.CDSE_CLIENT_SECRET}
            )
            token = token_r.json().get("access_token")
            r = await client.post(
                "https://sh.dataspace.copernicus.eu/api/v1/process",
                headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},
                json={
                    "input":{
                        "bounds":{"bbox":[minlng,minlat,maxlng,maxlat],"properties":{"crs":"http://www.opengis.net/def/crs/EPSG/0/4326"}},
                        "data":[{"type":"sentinel-2-l2a","dataFilter":{"timeRange":{"from":t_start,"to":t_end},"maxCloudCoverage":80,"mosaickingOrder":"leastCC"}}]
                    },
                    "evalscript":evalscript,
                    "output":{"width":256,"height":256,"responses":[{"identifier":"default","format":{"type":"image/png"}}]}
                }
            )
        img = Image.open(io.BytesIO(r.content)).convert("L")
        arr = np.array(img).astype(float)
        ndvi = (arr/127.5)-1.0
        veg_mask = ndvi > 0.1
        veg_pixels = ndvi[veg_mask]
        out = np.zeros((256,256,4), dtype=np.uint8)
        if len(veg_pixels) > 10:
            p_low = np.percentile(veg_pixels, 25)
            p_high = np.percentile(veg_pixels, 75)
            out[veg_mask & (ndvi>=p_high)] = [22,163,74,180]
            out[veg_mask & (ndvi>=p_low) & (ndvi<p_high)] = [217,119,6,180]
            out[veg_mask & (ndvi<p_low)] = [220,38,38,180]
        zone_img = Image.fromarray(out,'RGBA')
        buf = io.BytesIO()
        zone_img.save(buf, format='PNG')
        return Response(content=buf.getvalue(), media_type='image/png')
    except Exception:
        img = Image.new('RGBA',(256,256),(0,0,0,0))
        buf = io.BytesIO()
        img.save(buf,format='PNG')
        return Response(content=buf.getvalue(),media_type='image/png')

@app.get("/zone_tile")
async def zone_tile(
    minlng: float = -9.5,
    minlat: float = 52.0,
    maxlng: float = -9.4,
    maxlat: float = 52.1,
    time: str = "2026-04-01/2026-06-03"
):
    """Returns a relative variability zone PNG — zones based on field's own NDVI distribution."""
    import httpx, io, numpy as np
    from PIL import Image
    from config.settings import settings
    from fastapi.responses import Response

    # Get NDVI PNG from CDSE
    evalscript = """//VERSION=3
function setup(){
  return{input:[{bands:["B04","B08"],units:"REFLECTANCE"}],output:{bands:1,sampleType:"UINT8"}}
}
function evaluatePixel(s){
  var ndvi=(s.B08-s.B04)/(s.B08+s.B04+0.0001);
  return[Math.round((ndvi+1)*127.5)];
}"""

    t0, t1 = time.split("/")
    async with httpx.AsyncClient(timeout=30) as client:
        token_r = await client.post(
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
            data={"grant_type":"client_credentials","client_id":settings.CDSE_CLIENT_ID,"client_secret":settings.CDSE_CLIENT_SECRET}
        )
        token = token_r.json().get("access_token")
        r = await client.post(
            "https://sh.dataspace.copernicus.eu/api/v1/process",
            headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},
            json={
                "input":{
                    "bounds":{"bbox":[minlng,minlat,maxlng,maxlat],"properties":{"crs":"http://www.opengis.net/def/crs/EPSG/0/4326"}},
                    "data":[{"type":"sentinel-2-l2a","dataFilter":{"timeRange":{"from":f"{t0}T00:00:00Z","to":f"{t1}T23:59:59Z"},"maxCloudCoverage":80,"mosaickingOrder":"leastCC"}}]
                },
                "evalscript": evalscript,
                "output":{"width":256,"height":256,"responses":[{"identifier":"default","format":{"type":"image/png"}}]}
            }
        )

    # Decode NDVI
    img = Image.open(io.BytesIO(r.content)).convert("L")
    arr = np.array(img).astype(float)
    ndvi = (arr / 127.5) - 1.0

    # Mask non-vegetated pixels
    veg_mask = ndvi > 0.1

    # Calculate field-relative percentile breaks
    veg_pixels = ndvi[veg_mask]
    if len(veg_pixels) < 10:
        return Response(content=r.content, media_type="image/png")

    p_low  = np.percentile(veg_pixels, 25)
    p_high = np.percentile(veg_pixels, 75)

    # Create RGB zone image
    out = np.zeros((256, 256, 4), dtype=np.uint8)

    # High zone — green
    high = veg_mask & (ndvi >= p_high)
    out[high] = [22, 163, 74, 200]

    # Medium zone — amber
    med = veg_mask & (ndvi >= p_low) & (ndvi < p_high)
    out[med] = [217, 119, 6, 200]

    # Low zone — red
    low = veg_mask & (ndvi < p_low)
    out[low] = [220, 38, 38, 200]

    # Non-veg — transparent
    out[~veg_mask] = [0, 0, 0, 0]

    zone_img = Image.fromarray(out, 'RGBA')
    buf = io.BytesIO()
    zone_img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.read(), media_type="image/png")

@app.get("/test_historical")
async def test_historical(lat: float = 52.10, lng: float = -9.40):
    from extractors.cdse_historical_extractor import CDSEHistoricalExtractor
    e = CDSEHistoricalExtractor()
    r = await e.extract(lat, lng, years=5)
    return r

@app.get("/test_trend")
async def test_trend(lat: float = 52.10, lng: float = -9.40):
    from extractors.cdse_trend_extractor import CDSETrendExtractor
    e = CDSETrendExtractor()
    r = await e.extract(lat, lng)
    return r

@app.get("/test_cdse")
async def test_cdse(lat: float = 52.05, lng: float = -9.35):
    from extractors.cdse_optical_extractor import CDSEOpticalExtractor
    e = CDSEOpticalExtractor()
    r = await e.extract(lat, lng)
    return r

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
        # Weather + grass model
        try:
            weather = get_weather_data(req.lat, req.lng)
            ndvi = result.get('vegetation', {}).get('ndvi')
            rvi = result.get('sar', {}).get('rvi')
            smap = result.get('soil_moisture', {}).get('smap', {}).get('sm_surface_m3')
            grass = estimate_grass_cover(ndvi, rvi, smap, weather)
            result['weather'] = weather
            result['grass_model'] = grass
        except Exception as e:
            result['weather'] = {'available': False, 'error': str(e)}
            result['grass_model'] = {'available': False}
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/wms_proxy")
async def wms_proxy(
    request: Request,
    z: int = 14, x: int = 7764, y: int = 5404,
    layer: str = "TRUE_COLOR",
    time: str = ""
):
    """Proxy Sentinel Hub WMS tiles with OAuth token."""
    import httpx, datetime as dt
    from config.settings import settings
    from fastapi.responses import Response

    if not time:
        now = dt.datetime.utcnow()
        time = f"{(now - dt.timedelta(days=60)).strftime('%Y-%m-%d')}/{now.strftime('%Y-%m-%d')}"

    # Get token
    async with httpx.AsyncClient(timeout=15) as client:
        tr = await client.post(
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
            data={"grant_type":"client_credentials","client_id":settings.CDSE_CLIENT_ID,"client_secret":settings.CDSE_CLIENT_SECRET}
        )
        token = tr.json().get("access_token")

        # Convert XYZ to bbox
        import math
        n = 2**z
        lon_min = x/n*360 - 180
        lon_max = (x+1)/n*360 - 180
        lat_max = math.degrees(math.atan(math.sinh(math.pi*(1-2*y/n))))
        lat_min = math.degrees(math.atan(math.sinh(math.pi*(1-2*(y+1)/n))))

        evalscript = """//VERSION=3
function setup(){return{input:[{bands:["B02","B03","B04"],units:"REFLECTANCE"}],output:{bands:3,sampleType:"UINT8"}}}
function evaluatePixel(s){
  // Sentinel Hub viewer-quality enhancement
  var r=s.B04, g=s.B03, b=s.B02;
  // Linear stretch + gamma matching Sentinel Hub viewer
  r=Math.min(1,(r-0.0)*3.5); g=Math.min(1,(g-0.0)*3.5); b=Math.min(1,(b-0.0)*3.5);
  r=Math.pow(Math.max(0,r),0.75); g=Math.pow(Math.max(0,g),0.75); b=Math.pow(Math.max(0,b),0.75);
  return[Math.round(r*255),Math.round(g*255),Math.round(b*255)];
}"""
        t0,t1 = time.split("/") if "/" in time else (time,time)
        r = await client.post(
            "https://sh.dataspace.copernicus.eu/api/v1/process",
            headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},
            json={
                "input":{
                    "bounds":{"bbox":[lon_min,lat_min,lon_max,lat_max],"properties":{"crs":"http://www.opengis.net/def/crs/EPSG/0/4326"}},
                    "data":[{"type":"sentinel-2-l2a","dataFilter":{"timeRange":{"from":f"{t0}T00:00:00Z","to":f"{t1}T23:59:59Z"},"maxCloudCoverage":30,"mosaickingOrder":"leastCC"}}]
                },
                "evalscript":evalscript,
                "output":{"width":1024,"height":1024,"responses":[{"identifier":"default","format":{"type":"image/jpeg","quality":95}}]}
            }
        )
    return Response(content=r.content, media_type="image/jpeg")

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

INSTANCE_ID = "bfba5ae1-06b9-41d1-b2eb-771c247f9ac9"

@app.get("/wms_tile")
async def wms_tile(
    minlng: float = -9.5,
    minlat: float = 52.0,
    maxlng: float = -9.4,
    maxlat: float = 52.1,
    time: str = "",
    style: str = "rgb"
):
    """Sentinel-2 tile via Process API. style=rgb|ndvi"""
    import datetime as dt
    if not time:
        now = dt.datetime.utcnow()
        time = f"{(now - dt.timedelta(days=60)).strftime('%Y-%m-%d')}/{now.strftime('%Y-%m-%d')}"
    import httpx
    from config.settings import settings
    from fastapi.responses import Response

    if style == "ndvi":
        evalscript = """//VERSION=3
function setup(){return{input:["B04","B08"],output:{bands:3,sampleType:"UINT8"}}}
function evaluatePixel(s){
  var ndvi=(s.B08-s.B04)/(s.B08+s.B04+0.0001);
  if(ndvi>0.75) return [0,200,50];
  if(ndvi>0.60) return [50,180,0];
  if(ndvi>0.45) return [150,210,0];
  if(ndvi>0.30) return [230,200,0];
  if(ndvi>0.15) return [230,120,0];
  return [200,30,0];
}"""
    elif style == "zones":
        evalscript = """//VERSION=3
function setup(){return{input:["B04","B08"],output:{bands:3,sampleType:"UINT8"}}}
function evaluatePixel(s){
  var ndvi=(s.B08-s.B04)/(s.B08+s.B04+0.0001);
  // Hard zone boundaries: green/amber/red
  if(ndvi>0.65) return [0,180,0];
  if(ndvi>0.45) return [200,160,0];
  return [200,0,0];
}"""
    else:
        evalscript = """//VERSION=3
function setup(){
  return{
    input:[{bands:["B02","B03","B04"],units:"REFLECTANCE"}],
    output:{bands:3,sampleType:"UINT8"}
  }
}
function evaluatePixel(s){
  // Highlight Optimized Natural Color
  var r=s.B04, g=s.B03, b=s.B02;
  // Gain and gamma correction
  var gain=3.5, gamma=0.85;
  r=Math.pow(Math.min(1,r*gain),gamma);
  g=Math.pow(Math.min(1,g*gain),gamma);
  b=Math.pow(Math.min(1,b*gain),gamma);
  // Contrast stretch
  var min=0.05, max=0.95;
  r=(r-min)/(max-min);
  g=(g-min)/(max-min);
  b=(b-min)/(max-min);
  return[
    Math.round(Math.max(0,Math.min(1,r))*255),
    Math.round(Math.max(0,Math.min(1,g))*255),
    Math.round(Math.max(0,Math.min(1,b))*255)
  ];
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
                "output":{"width":2048,"height":2048,"responses":[{"identifier":"default","format":{"type":"image/jpeg","quality":90}}]}
            }
        )
        return Response(content=process_r.content,media_type="image/jpeg")


# wms_proxy added Wed Jun  3 14:35:37 UTC 2026
# Force redeploy Wed Jun  3 20:37:53 UTC 2026
# redeploy Fri Jun  5 04:44:01 UTC 2026

@app.post("/analyse_photo")
async def analyse_photo(request: Request):
    import anthropic, os, json
    body = await request.json()
    image_data = body.get("image_data")
    if not image_data:
        return {"error": "no image"}
    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                    {"type": "text", "text": "You are an expert Irish grassland agronomist. Analyse this field photo. Respond ONLY in JSON: {\"detected\":\"main issue in 2-4 words\",\"confidence\":82,\"species\":[\"species1\"],\"recommendation\":\"one clear action sentence\",\"issue_type\":\"weeds|compaction|thin_sward|overgrazing|drainage|healthy|other\"}"}
                ]
            }]
        )
        text = message.content[0].text
        return json.loads(text.replace("```json","").replace("```","").strip())
    except Exception as e:
        return {"error": str(e)}

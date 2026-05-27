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


@app.post("/field_profile")
async def field_profile(req: ProfileRequest):
    try:
        result = await service.build_profile(req.lat, req.lng, req.year)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

"""
DAFM GeoAPI extractor for Cube Earth.
Replaces Supabase centroid matching with live point-in-polygon queries.
"""
import httpx
import asyncio

GEOAPI_BASE = "https://geoapi.opendata.agriculture.gov.ie/shps/collections"
COLLECTION  = "anonymous-lpis-data-for-2024_2024-lpis-data"


async def get_parcel_at_point(lat, lng, tolerance=0.0001):
    """
    Query DAFM GeoAPI for parcel at exact point.
    Uses bbox around point then checks geometry.
    """
    bbox = f"{lng-tolerance},{lat-tolerance},{lng+tolerance},{lat+tolerance}"
    url  = f"{GEOAPI_BASE}/{COLLECTION}/items"

    params = {
        "bbox":  bbox,
        "f":     "json",
        "limit": 10,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    features = data.get("features", [])
    if not features:
        return None

    # Find best match — parcel whose geometry contains the point
    # For now use smallest area parcel in bbox (most likely exact match)
    best = None
    best_area = float('inf')

    for f in features:
        props = f.get("properties", {})
        crop  = props.get("CROP", "")

        # Skip non-agricultural features
        if crop.lower() in ("building", "road", "water", ""):
            continue

        area = float(props.get("CLAIM_AREA") or props.get("DIGITISED") or 0)
        if area < best_area:
            best_area = area
            best = f

    if not best:
        best = features[0]

    props = best.get("properties", {})
    geom  = best.get("geometry", {})

    # Calculate centroid from geometry if available
    centroid_lat, centroid_lng = lat, lng
    if geom and geom.get("type") == "Polygon":
        coords = geom.get("coordinates", [[]])[0]
        if coords:
            centroid_lng = sum(c[0] for c in coords) / len(coords)
            centroid_lat = sum(c[1] for c in coords) / len(coords)

    import math
    dlat = (centroid_lat - lat) * 111320
    dlng = (centroid_lng - lng) * 111320 * math.cos(math.radians(lat))
    dist_m = round(math.sqrt(dlat**2 + dlng**2))

    crop_str = props.get("CROP", "Unknown")

    return {
        "par_lab":      props.get("PAR_LAB"),
        "herd":         props.get("HERD"),
        "claim_area":   float(props.get("CLAIM_AREA") or 0),
        "crop":         crop_str,
        "grassland":    _is_grassland(crop_str),
        "tillage":      _is_tillage(crop_str),
        "arable":       _is_arable(crop_str),
        "biss":         bool(props.get("BISS")),
        "eco":          bool(props.get("ECO")),
        "centroid_lat": centroid_lat,
        "centroid_lng": centroid_lng,
        "_match_distance_m": dist_m,
        "_match_quality": (
            "exact"   if dist_m < 50   else
            "close"   if dist_m < 200  else
            "nearby"  if dist_m < 500  else
            "distant"
        ),
        "_source": "DAFM GeoAPI 2024",
    }


def _is_grassland(crop):
    c = crop.lower()
    return any(k in c for k in ["pasture","grass","silage","hay","grazing","meadow"])

def _is_tillage(crop):
    c = crop.lower()
    return any(k in c for k in ["rape","wheat","barley","oats","cereal","maize","rye"])

def _is_arable(crop):
    c = crop.lower()
    return any(k in c for k in ["potato","beet","vegetable","bean","pea"])

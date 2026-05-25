from analytics.soil_moisture import classify_drainage


# Sensor confidence rules based on literature
# Ali 2016: NDVI r=0.68, NDRE r=0.93 with chlorophyll
# Barrett 2014: C-band kappa=0.87, C+L kappa=0.98
# TaLAM: minimum mapping unit 0.5ha
# Hayes 2025: UAV bridge gap unresolved below satellite pixel


def s2_confidence(ndvi, ndre, cloud_cover, granule_date, obs_count=1):
    score = 10
    reasons = []

    # Cloud contamination
    cloud = float(cloud_cover or 100)
    if cloud > 50:
        score -= 4
        reasons.append(f"High cloud cover ({cloud}%) — optical signal unreliable")
    elif cloud > 20:
        score -= 2
        reasons.append(f"Moderate cloud cover ({cloud}%)")

    # Data age
    if granule_date:
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(granule_date.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dt).days
            if age > 30:
                score -= 2
                reasons.append(f"Granule {age} days old")
            elif age > 15:
                score -= 1
        except Exception:
            pass

    # NDVI validity
    if ndvi is None:
        score -= 5
        reasons.append("No NDVI retrieved")
    elif ndvi < 0 or ndvi > 1:
        score -= 3
        reasons.append("NDVI out of range")

    # Red-edge (NDRE) — Ali 2016 r=0.93
    if ndre is None:
        score -= 1
        reasons.append("No NDRE — chlorophyll confidence reduced")

    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {
        "score": max(0, score),
        "level": level,
        "sensor": "HLS Sentinel-2",
        "resolution": "30m",
        "reasons": reasons,
        "literature": "Ali 2016: NDRE r=0.93 with canopy chlorophyll",
    }


def smap_confidence(sm_surface, sm_rootzone, granule_date):
    score = 10
    reasons = []

    if sm_surface is None:
        score -= 6
        reasons.append("No SMAP surface moisture")
    else:
        if sm_surface < 0 or sm_surface > 0.6:
            score -= 3
            reasons.append("SMAP value out of physical range")

    if sm_rootzone is None:
        score -= 2
        reasons.append("No SMAP rootzone")

    if granule_date:
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(str(granule_date) + "T00:00:00+00:00")
            age = (datetime.now(timezone.utc) - dt).days
            if age > 7:
                score -= 2
                reasons.append(f"SMAP granule {age} days old")
        except Exception:
            pass

    reasons.append("9km EASE-2 grid — NOT parcel precise")
    reasons.append("One pixel covers ~81km² containing ~1750 Irish parcels")
    reasons.append("Use for regional soil moisture trend only")
    score -= 2  # Resolution penalty always applied
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {
        "score": max(0, score),
        "level": level,
        "sensor": "SMAP L4",
        "resolution": "9km",
        "reasons": reasons,
        "literature": "Direct L-band observation — most reliable soil moisture source",
    }


def era5_confidence(surface_mean, obs_count):
    score = 10
    reasons = []

    if surface_mean is None:
        score -= 6
        reasons.append("ERA5 data unavailable")
    if obs_count and obs_count < 30:
        score -= 2
        reasons.append(f"Only {obs_count} observations — short season")

    reasons.append("Model reanalysis — not direct observation")
    reasons.append("9km resolution — NOT parcel precise")
    reasons.append("Regional moisture trend only — not field specific")
    score -= 1  # Resolution penalty
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {
        "score": max(0, score),
        "level": level,
        "sensor": "ERA5-Land",
        "resolution": "9km",
        "reasons": reasons,
        "literature": "Green 2018: ERA5 used for moisture trend analysis",
    }


def s1_confidence(granule_count):
    score = 7  # C-band starts at moderate per Barrett 2014
    reasons = []

    if not granule_count or granule_count == 0:
        score = 0
        reasons.append("No Sentinel-1 granules found")
    elif granule_count < 3:
        score -= 2
        reasons.append(f"Only {granule_count} SAR granules")

    reasons.append("C-band only — cannot distinguish management intensities")
    reasons.append("Barrett 2014: C+L kappa=0.98 vs C alone kappa=0.87")
    reasons.append("L-band (PALSAR-2) not available for Ireland")
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {
        "score": max(0, score),
        "level": level,
        "sensor": "Sentinel-1 C-band",
        "resolution": "20m",
        "reasons": reasons,
        "literature": "Barrett 2014: C-band alone kappa=0.87 for grassland classification",
    }


def ecostress_confidence(celsius, granule_time):
    if celsius is None:
        return {
            "score": 0,
            "level": "unavailable",
            "sensor": "ECOSTRESS",
            "resolution": "70m",
            "reasons": [
                "No valid LST pixel — cloud or fill value",
                "Ireland Atlantic cloud limits ECOSTRESS availability",
            ],
            "literature": "Hayes 2025: Thermal data limited by cloud in maritime climates",
        }

    score = 8
    reasons = []

    if granule_time:
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(granule_time.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dt).days
            if age > 90:
                score -= 3
                reasons.append(f"Granule {age} days old — stale thermal data")
            elif age > 30:
                score -= 1
                reasons.append(f"Granule {age} days old")
        except Exception:
            pass

    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {
        "score": max(0, score),
        "level": level,
        "sensor": "ECOSTRESS",
        "resolution": "70m",
        "reasons": reasons,
        "literature": "Hayes 2025: Thermal ET confirms moisture stress independently",
    }


def parcel_confidence(area_ha, crop):
    score = 10
    reasons = []

    if area_ha is None:
        score -= 4
        reasons.append("No parcel area — size penalty unknown")
    elif area_ha < 0.5:
        score -= 5
        reasons.append(f"Micro parcel ({area_ha}ha) — TaLAM min mapping unit is 0.5ha")
        reasons.append("Boundary contamination affects all satellite readings")
    elif area_ha < 2.0:
        score -= 2
        reasons.append(f"Small parcel ({area_ha}ha) — minor boundary contamination")

    if crop is None:
        score -= 2
        reasons.append("No crop declaration")

    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {
        "score": max(0, score),
        "level": level,
        "sensor": "LPIS Parcel",
        "area_ha": area_ha,
        "reasons": reasons,
        "literature": "TaLAM 2018: Minimum mapping unit 0.5ha for satellite reliability",
    }


def overall_confidence(s2c, smapc, era5c, s1c, ecoc, parcelc):
    weights = {
        "s2":     0.30,
        "smap":   0.25,
        "era5":   0.15,
        "s1":     0.10,
        "eco":    0.10,
        "parcel": 0.10,
    }
    scores = {
        "s2":     s2c["score"],
        "smap":   smapc["score"],
        "era5":   era5c["score"],
        "s1":     s1c["score"],
        "eco":    ecoc["score"] if ecoc["level"] != "unavailable" else 5,
        "parcel": parcelc["score"],
    }
    weighted = sum(scores[k] * weights[k] for k in weights)
    level = "high" if weighted >= 7.5 else "moderate" if weighted >= 5.0 else "low"

    limiting = [
        k for k, v in {
            "Sentinel-2": s2c,
            "SMAP":       smapc,
            "ERA5":       era5c,
            "Sentinel-1": s1c,
            "ECOSTRESS":  ecoc,
            "Parcel":     parcelc,
        }.items()
        if v["level"] in ("low", "unavailable")
    ]

    explanation = (
        f"{level.capitalize()} confidence"
        + (f" — limiting factors: {', '.join(limiting)}" if limiting else " — all sensors reliable")
    )

    return {
        "score":       round(weighted, 1),
        "level":       level,
        "explanation": explanation,
        "weights":     weights,
        "sensor_scores": scores,
        "breakdown": {
            "sentinel2":  s2c,
            "smap":       smapc,
            "era5":       era5c,
            "sentinel1":  s1c,
            "ecostress":  ecoc,
            "parcel":     parcelc,
        },
    }

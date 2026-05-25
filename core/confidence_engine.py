from datetime import datetime, timezone


def _age_days(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None

def _age_penalty(age, thresholds):
    if age is None:
        return 2
    for days, penalty in thresholds:
        if age <= days:
            return penalty
    return 5

def _age_label(age):
    if age is None: return "unknown"
    if age == 0:    return "today"
    if age == 1:    return "1 day old"
    return f"{age} days old"


def s2_confidence(ndvi, ndre, cloud_cover, granule_date, obs_count=1):
    score = 10
    reasons = []
    cloud = float(cloud_cover or 100)
    if cloud > 50:
        score -= 4
        reasons.append(f"High cloud cover ({cloud}%)")
    elif cloud > 20:
        score -= 2
        reasons.append(f"Moderate cloud cover ({cloud}%)")
    age = _age_days(granule_date)
    penalty = _age_penalty(age, [(2,0),(7,0.5),(15,1),(30,2),(60,3),(90,4)])
    score -= penalty
    if penalty > 0:
        reasons.append(f"Granule {_age_label(age)} — age penalty -{penalty}")
    if ndvi is None:
        score -= 5
        reasons.append("No NDVI retrieved")
    if ndre is None:
        score -= 1
        reasons.append("No NDRE — chlorophyll confidence reduced")
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {"score": round(max(0,score),1), "level": level,
            "sensor": "HLS Sentinel-2", "resolution": "30m",
            "age_days": age, "age_label": _age_label(age),
            "reasons": reasons,
            "literature": "Ali 2016: NDRE r=0.93 with canopy chlorophyll"}


def smap_confidence(sm_surface, sm_rootzone, granule_date):
    score = 10
    reasons = []
    if sm_surface is None:
        score -= 6
        reasons.append("No SMAP surface moisture")
    elif sm_surface < 0 or sm_surface > 0.6:
        score -= 3
        reasons.append("SMAP value out of physical range")
    if sm_rootzone is None:
        score -= 2
        reasons.append("No SMAP rootzone")
    age = _age_days(granule_date)
    penalty = _age_penalty(age, [(2,0),(7,0.5),(14,1),(30,2)])
    score -= penalty
    if penalty > 0:
        reasons.append(f"Granule {_age_label(age)} — age penalty -{penalty}")
    score -= 2
    reasons.append("9km EASE-2 grid — NOT parcel precise")
    reasons.append("One pixel covers ~81km2 — regional indicator only")
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {"score": round(max(0,score),1), "level": level,
            "sensor": "SMAP L4", "resolution": "9km",
            "age_days": age, "age_label": _age_label(age),
            "reasons": reasons,
            "literature": "Direct L-band observation — most reliable regional soil moisture"}


def era5_confidence(surface_mean, obs_count):
    score = 10
    reasons = []
    if surface_mean is None:
        score -= 6
        reasons.append("ERA5 data unavailable")
    if obs_count and obs_count < 30:
        score -= 2
        reasons.append(f"Only {obs_count} observations — short season")
    score -= 1
    reasons.append("Model reanalysis — not direct observation")
    reasons.append("9km resolution — NOT parcel precise")
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {"score": round(max(0,score),1), "level": level,
            "sensor": "ERA5-Land", "resolution": "9km",
            "age_days": None, "age_label": "current trend",
            "reasons": reasons,
            "literature": "Green 2018: ERA5 used for seasonal moisture trend analysis"}


def s1_confidence(granule_count, latest_date=None):
    score = 7
    reasons = []
    if not granule_count or granule_count == 0:
        score = 0
        reasons.append("No Sentinel-1 granules found")
    elif granule_count < 3:
        score -= 2
        reasons.append(f"Only {granule_count} SAR granules")
    age = _age_days(latest_date)
    penalty = _age_penalty(age, [(2,0),(7,0.5),(15,1),(30,2)])
    score -= penalty
    if penalty > 0:
        reasons.append(f"Latest granule {_age_label(age)}")
    reasons.append("Granule presence confirmed — VV/VH backscatter not yet extracted")
    reasons.append("C-band only — cannot distinguish management intensities")
    reasons.append("Barrett 2014: C+L kappa=0.98 vs C alone kappa=0.87")
    reasons.append("Score capped until pixel extraction implemented")
    score = min(score, 6)  # cap until actual signal extracted
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {"score": round(max(0,score),1), "level": level,
            "sensor": "Sentinel-1 C-band", "resolution": "20m",
            "age_days": age, "age_label": _age_label(age),
            "reasons": reasons,
            "literature": "Barrett 2014: C-band alone kappa=0.87 for grassland classification"}


def ecostress_confidence(celsius, granule_time):
    age = _age_days(granule_time)
    if celsius is None:
        return {"score": 0, "level": "unavailable",
                "sensor": "ECOSTRESS", "resolution": "70m",
                "age_days": None, "age_label": "no data",
                "reasons": ["No valid LST pixel — cloud or fill value",
                            "Ireland Atlantic cloud limits ECOSTRESS availability"],
                "literature": "Hayes 2025: Thermal data limited by cloud in maritime climates"}
    score = 8
    reasons = []
    penalty = _age_penalty(age, [(5,0),(15,1),(30,2),(60,3),(90,4)])
    score -= penalty
    if penalty > 0:
        reasons.append(f"Granule {_age_label(age)} — age penalty -{penalty}")
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {"score": round(max(0,score),1), "level": level,
            "sensor": "ECOSTRESS", "resolution": "70m",
            "age_days": age, "age_label": _age_label(age),
            "reasons": reasons,
            "literature": "Hayes 2025: Thermal ET confirms moisture stress independently"}


def parcel_confidence(area_ha, crop):
    score = 10
    reasons = []
    if area_ha is None:
        score -= 4
        reasons.append("No parcel area — size penalty unknown")
    elif area_ha < 0.5:
        score -= 6
        reasons.append(f"Micro parcel ({area_ha}ha) — below TaLAM 0.5ha minimum")
        reasons.append("Boundary contamination affects ALL satellite readings")
    elif area_ha < 2.0:
        score -= 3
        reasons.append(f"Small parcel ({area_ha}ha) — boundary contamination likely")
    elif area_ha < 5.0:
        score -= 1
        reasons.append(f"Medium parcel ({area_ha}ha) — minor edge effects")
    if crop is None:
        score -= 2
        reasons.append("No crop declaration in LPIS")
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    return {"score": round(max(0,score),1), "level": level,
            "sensor": "LPIS Parcel", "area_ha": area_ha,
            "reasons": reasons,
            "literature": "TaLAM 2018: Minimum mapping unit 0.5ha for satellite reliability"}


def cross_sensor_agreement(ndvi, smap_surf, era5_surf, s1_granules):
    # Start at 8.0 — sensors measure different things by design
    # 10/10 reserved for strong active consistency evidence
    score = 8.0
    flags = []
    agreements = []

    # SMAP vs ERA5 moisture
    if smap_surf is not None and era5_surf is not None:
        diff = abs(smap_surf - era5_surf)
        if diff > 0.15:
            score -= 2
            flags.append(f"SMAP ({smap_surf:.3f}) and ERA5 ({era5_surf:.3f}) disagree by {diff:.3f} m3/m3")
        elif diff > 0.08:
            score -= 0.5
            flags.append(f"Minor moisture disagreement SMAP vs ERA5 ({diff:.3f} m3/m3)")
        else:
            score += 0.5  # active evidence of consistency
            agreements.append(f"SMAP and ERA5 moisture consistent (diff {diff:.3f} m3/m3)")
    else:
        score -= 1
        flags.append("Cannot compare SMAP vs ERA5 — one unavailable")

    # NDVI vs moisture
    if ndvi is not None and smap_surf is not None:
        if ndvi > 0.75 and smap_surf < 0.18:
            score -= 2
            flags.append("High NDVI but low soil moisture — possible deep-root access")
        elif ndvi < 0.35 and smap_surf > 0.38:
            score -= 2
            flags.append("Low vegetation but high moisture — possible waterlogging or recent cut")
        else:
            score += 0.5  # active evidence
            agreements.append(f"NDVI {ndvi:.2f} consistent with soil moisture {smap_surf:.3f}")
    else:
        score -= 0.5
        flags.append("Cannot cross-check NDVI vs moisture — data missing")

    # SAR — granule existence only, no pixel extraction yet
    if not s1_granules or s1_granules == 0:
        score -= 1
        flags.append("No SAR granules found — optical-only assessment")
    else:
        # Granules confirmed but VV/VH backscatter not extracted
        # Cannot claim structural signal until pixel values computed
        agreements.append(
            f"SAR granules available ({s1_granules}) — "
            f"VV/VH not extracted, structural signal unconfirmed"
        )
        # No score bonus until actual backscatter contributes to fusion

    score = min(10, max(0, score))
    level = "high" if score >= 8 else "moderate" if score >= 5 else "low"
    note = (flags[0] if flags
            else f"Sensors consistent — {len(agreements)} agreement(s) confirmed")
    return {"score": round(score, 1), "level": level,
            "agreements": agreements, "flags": flags, "note": note}


def freshness_summary(s2_date, smap_date, s1_date, eco_date):
    def entry(name, date, resolution):
        age = _age_days(date)
        return {"sensor": name,
                "date": str(date)[:10] if date else None,
                "age_days": age, "age_label": _age_label(age),
                "resolution": resolution,
                "freshness": ("current" if age is not None and age <= 3
                              else "recent" if age is not None and age <= 14
                              else "moderate" if age is not None and age <= 30
                              else "stale" if age is not None else "no_data")}
    return {
        "sentinel2":  entry("Sentinel-2", s2_date, "30m"),
        "smap":       entry("SMAP L4",    smap_date, "9km"),
        "sentinel1":  entry("Sentinel-1", s1_date, "20m"),
        "ecostress":  entry("ECOSTRESS",  eco_date, "70m"),
        "era5":       {"sensor": "ERA5-Land", "age_label": "seasonal context",
                       "resolution": "9km", "freshness": "seasonal_context",
                       "note": "ERA5 provides seasonal trend — not parcel current moisture"},
    }


def explainability(grazing, traffic, slurry, drought, waterlog,
                   ndvi, gcap, surf_use, root_use, slope, drainage,
                   s2_age=None, smap_age=None, era5_age=None):

    def age_note(age):
        if age is None: return ""
        if age <= 1: return " (1 day old)"
        if age <= 7: return f" ({age} days old)"
        return f" ({age} days old — verify current conditions)"

    def build(label, score, reasons):
        return {"label": label, "score": score, "because": reasons}

    grazing_reasons = []
    if ndvi is not None:
        grazing_reasons.append(
            f"NDVI {ndvi:.2f}{age_note(s2_age)} — "
            f"{'good' if ndvi > 0.65 else 'moderate' if ndvi > 0.45 else 'low'} grass cover")
    if surf_use is not None:
        grazing_reasons.append(
            f"Soil moisture {surf_use:.3f} m3/m3{age_note(smap_age)} — "
            f"{'wet, poaching risk' if surf_use > 0.38 else 'adequate' if surf_use > 0.25 else 'dry'}")
    if slope is not None:
        grazing_reasons.append(
            f"Slope {slope:.1f}deg — "
            f"{'flat, easy access' if slope < 3 else 'moderate slope' if slope < 8 else 'steep'}")
    if waterlog["probability"] != "low":
        grazing_reasons.append(f"Waterlogging {waterlog['probability']} — limits grazing days")

    traffic_reasons = []
    if surf_use is not None:
        traffic_reasons.append(
            f"Surface moisture {surf_use:.3f}{age_note(smap_age)} — "
            f"{'excellent' if surf_use < 0.25 else 'good' if surf_use < 0.30 else 'moderate' if surf_use < 0.35 else 'poor, rutting risk'}")
    if root_use is not None:
        traffic_reasons.append(
            f"Rootzone {root_use:.3f} — "
            f"{'firm' if root_use < 0.28 else 'adequate' if root_use < 0.35 else 'soft'}")
    if slope is not None:
        traffic_reasons.append(
            f"Slope {slope:.1f}deg — "
            f"{'flat' if slope < 2 else 'gentle' if slope < 6 else 'challenging'}")

    slurry_reasons = []
    if surf_use is not None:
        slurry_reasons.append(
            f"Soil moisture {surf_use:.3f}{age_note(smap_age)} — "
            f"{'too wet, leaching risk' if surf_use > 0.40 else 'near capacity, caution' if surf_use > 0.35 else 'acceptable'}")
    if slope is not None and slope > 5:
        slurry_reasons.append(f"Slope {slope:.1f}deg — runoff risk elevated")
    if drainage != "good":
        slurry_reasons.append(f"Drainage {drainage} — increases runoff risk")

    drought_reasons = []
    if surf_use is not None:
        drought_reasons.append(f"Surface moisture {surf_use:.3f} m3/m3{age_note(smap_age)}")
    if root_use is not None:
        drought_reasons.append(f"Rootzone moisture {root_use:.3f} m3/m3")
    if ndvi is not None:
        drought_reasons.append(f"NDVI {ndvi:.2f}{age_note(s2_age)} — vegetation response")

    return {
        "grazing":   build(grazing["label"], grazing["score"], grazing_reasons),
        "machinery": build(traffic["label"], traffic["score"], traffic_reasons),
        "slurry":    build(slurry["suitable"], None, slurry_reasons),
        "drought":   build(drought["label"], drought["score"], drought_reasons),
    }


def overall_confidence(s2c, smapc, era5c, s1c, ecoc, parcelc, agreement):
    weights = {"s2": 0.28, "smap": 0.22, "era5": 0.13, "s1": 0.10,
               "eco": 0.08, "parcel": 0.10, "agreement": 0.09}
    scores  = {"s2": s2c["score"], "smap": smapc["score"], "era5": era5c["score"],
               "s1": s1c["score"],
               "eco": ecoc["score"] if ecoc["level"] != "unavailable" else 5,
               "parcel": parcelc["score"], "agreement": agreement["score"]}
    weighted = sum(scores[k] * weights[k] for k in weights)
    level = "high" if weighted >= 7.5 else "moderate" if weighted >= 5.0 else "low"
    limiting = [k for k, v in {"Sentinel-2": s2c, "SMAP": smapc, "ERA5": era5c,
                                "Sentinel-1": s1c, "ECOSTRESS": ecoc,
                                "Parcel": parcelc}.items()
                if v["level"] in ("low", "unavailable")]
    explanation = (f"{level.capitalize()} confidence"
                   + (f" — limiting: {', '.join(limiting)}" if limiting
                      else " — all sensors reliable"))
    return {"score": round(weighted,1), "level": level, "explanation": explanation,
            "weights": weights, "sensor_scores": scores,
            "breakdown": {"sentinel2": s2c, "smap": smapc, "era5": era5c,
                          "sentinel1": s1c, "ecostress": ecoc,
                          "parcel": parcelc, "agreement": agreement}}

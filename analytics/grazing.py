def grazing_suitability(surface_sm, slope, waterlog_prob, area_ha):
    score = 0
    if surface_sm is not None:
        if 0.25 < surface_sm < 0.38: score += 3
        elif 0.20 <= surface_sm <= 0.42: score += 2
        elif surface_sm < 0.20: score += 1
    if (slope or 0) < 3: score += 2
    elif (slope or 0) < 8: score += 1
    if waterlog_prob == "high": score = max(0, score - 3)
    elif waterlog_prob == "moderate": score = max(0, score - 1)
    label = (
        "Excellent" if score >= 8 else
        "Good"      if score >= 6 else
        "Moderate"  if score >= 4 else
        "Poor"      if score >= 2 else
        "Not suitable"
    )
    note = None
    if area_ha and area_ha < 0.5:
        note = "Small parcel limits practical grazing management"
    return {"score": score, "label": label, "note": note}

def machinery_trafficability(surface_sm, rootzone_sm, slope):
    score = 0
    if surface_sm is not None:
        if surface_sm < 0.25: score += 4
        elif surface_sm < 0.30: score += 3
        elif surface_sm < 0.35: score += 2
        elif surface_sm < 0.40: score += 1
    if rootzone_sm is not None:
        if rootzone_sm < 0.28: score += 3
        elif rootzone_sm < 0.33: score += 2
        elif rootzone_sm < 0.38: score += 1
    if (slope or 0) < 2: score += 3
    elif (slope or 0) < 6: score += 2
    elif (slope or 0) < 12: score += 1
    label = (
        "Excellent"                          if score >= 8 else
        "Good"                               if score >= 6 else
        "Moderate - proceed with caution"    if score >= 4 else
        "Poor - risk of rutting/compaction"  if score >= 2 else
        "Unsuitable - do not operate machinery"
    )
    return {"score": score, "label": label}

def slurry_suitability(surface_sm, slope, traffic_score):
    if surface_sm and surface_sm > 0.40:
        return {"suitable": "not_suitable",
                "note": "Waterlogged - high runoff and leaching risk"}
    if (slope or 0) > 10:
        return {"suitable": "not_suitable",
                "note": "Slope exceeds 10deg - unacceptable runoff risk"}
    if traffic_score < 3:
        return {"suitable": "not_suitable",
                "note": "Ground too wet for machinery access"}
    if surface_sm and surface_sm > 0.35:
        return {"suitable": "caution",
                "note": "Near field capacity - monitor for runoff"}
    return {"suitable": "suitable",
            "note": "Conditions acceptable for spreading"}

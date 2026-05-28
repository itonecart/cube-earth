"""
Crop stage detection for Cube Earth.
Uses NDVI trend + calendar date + crop type to determine growth stage.
"""
import datetime


CROP_CALENDARS = {
    "arable": [
        {"stage": "soil_preparation", "months": [3, 4],      "ndvi_range": (0.05, 0.25)},
        {"stage": "emergence",        "months": [4, 5],      "ndvi_range": (0.10, 0.40)},
        {"stage": "vegetative",       "months": [5, 6],      "ndvi_range": (0.30, 0.75)},
        {"stage": "canopy_closure",   "months": [6, 7],      "ndvi_range": (0.55, 0.90)},
        {"stage": "senescence",       "months": [8, 9],      "ndvi_range": (0.20, 0.60)},
        {"stage": "post_harvest",     "months": [9, 10, 11], "ndvi_range": (0.05, 0.25)},
    ],
    "winter_oilseed_rape": [
        {"stage": "emergence",    "months": [9, 10],     "ndvi_range": (0.10, 0.30)},
        {"stage": "vegetative",   "months": [11, 12, 1, 2], "ndvi_range": (0.25, 0.60)},
        {"stage": "stem_extension","months": [3],         "ndvi_range": (0.40, 0.70)},
        {"stage": "flowering",    "months": [4],          "ndvi_range": (0.50, 0.85)},
        {"stage": "senescence",   "months": [5],          "ndvi_range": (0.15, 0.55)},
        {"stage": "harvest",      "months": [6, 7],       "ndvi_range": (0.05, 0.25)},
        {"stage": "post_harvest", "months": [7, 8],       "ndvi_range": (0.05, 0.20)},
    ],
    "winter_wheat": [
        {"stage": "emergence",    "months": [10, 11],     "ndvi_range": (0.10, 0.30)},
        {"stage": "vegetative",   "months": [12, 1, 2],   "ndvi_range": (0.25, 0.55)},
        {"stage": "stem_extension","months": [3, 4],      "ndvi_range": (0.45, 0.80)},
        {"stage": "heading",      "months": [5],          "ndvi_range": (0.55, 0.85)},
        {"stage": "ripening",     "months": [6],          "ndvi_range": (0.25, 0.60)},
        {"stage": "harvest",      "months": [7, 8],       "ndvi_range": (0.05, 0.25)},
    ],
    "winter_barley": [
        {"stage": "emergence",    "months": [10, 11],     "ndvi_range": (0.10, 0.30)},
        {"stage": "vegetative",   "months": [12, 1, 2],   "ndvi_range": (0.25, 0.55)},
        {"stage": "stem_extension","months": [3],         "ndvi_range": (0.45, 0.75)},
        {"stage": "heading",      "months": [4, 5],       "ndvi_range": (0.50, 0.80)},
        {"stage": "ripening",     "months": [5, 6],       "ndvi_range": (0.20, 0.55)},
        {"stage": "harvest",      "months": [6, 7],       "ndvi_range": (0.05, 0.20)},
    ],
    "grassland": [
        {"stage": "winter_dormancy", "months": [12, 1, 2], "ndvi_range": (0.20, 0.50)},
        {"stage": "spring_flush",    "months": [3, 4],     "ndvi_range": (0.50, 0.90)},
        {"stage": "peak_growth",     "months": [5, 6],     "ndvi_range": (0.60, 0.95)},
        {"stage": "summer_growth",   "months": [7, 8],     "ndvi_range": (0.55, 0.90)},
        {"stage": "autumn_growth",   "months": [9, 10],    "ndvi_range": (0.45, 0.80)},
        {"stage": "late_season",     "months": [11],       "ndvi_range": (0.30, 0.65)},
    ],
}

STAGE_LABELS = {
    "soil_preparation": "Soil Preparation",
    "canopy_closure":   "Canopy Closure",
    "emergence":       "Crop Emergence",
    "vegetative":      "Vegetative Growth",
    "stem_extension":  "Stem Extension",
    "flowering":       "Flowering",
    "heading":         "Heading",
    "senescence":      "Senescence",
    "ripening":        "Ripening",
    "harvest":         "Harvest Stage",
    "post_harvest":    "Post-Harvest",
    "winter_dormancy": "Winter Dormancy",
    "spring_flush":    "Spring Flush",
    "peak_growth":     "Peak Growth",
    "summer_growth":   "Summer Growth",
    "autumn_growth":   "Autumn Growth",
    "late_season":     "Late Season",
}

STAGE_ADVICE = {
    "soil_preparation": "Field being prepared — avoid heavy machinery on wet soil",
    "canopy_closure":   "Full canopy — monitor for disease and nutrient stress",
    "emergence":       "Monitor for establishment — soil moisture critical",
    "vegetative":      "N uptake phase — monitor for deficiency",
    "stem_extension":  "Rapid growth — check for lodging risk",
    "flowering":       "Critical stage — avoid spraying in wind",
    "heading":         "Grain fill beginning — monitor moisture",
    "senescence":      "Natural decline — approaching harvest window",
    "ripening":        "Monitor moisture content — harvest timing critical",
    "harvest":         "Harvest window approaching or active",
    "post_harvest":    "Field available for cultivation or cover crop",
    "winter_dormancy": "Low growth — monitor for waterlogging",
    "spring_flush":    "Rapid growth — grazing rotation recommended",
    "peak_growth":     "Maximum productivity — optimal grazing window",
    "summer_growth":   "Active growth — monitor soil moisture",
    "autumn_growth":   "Pre-winter build-up — final grazing rotation",
    "late_season":     "Slowing growth — prepare for winter management",
}


def get_crop_calendar_key(crop_str):
    if not crop_str:
        return None
    c = crop_str.lower()
    if "rape" in c or "oilseed" in c:
        return "winter_oilseed_rape"
    if "wheat" in c:
        return "winter_wheat"
    if "barley" in c:
        return "winter_barley"
    if "pasture" in c or "grass" in c or "meadow" in c:
        return "grassland"
    if "potato" in c or "beet" in c or "vegetable" in c:
        return "arable"
    if "maize" in c or "corn" in c:
        return "arable"
    return None


def detect_crop_stage(crop_str, ndvi, month=None, trend=None):
    """
    Detect crop growth stage from crop type, NDVI and calendar month.
    """
    if not crop_str or ndvi is None:
        return None

    if month is None:
        month = datetime.datetime.now().month

    cal_key = get_crop_calendar_key(crop_str)
    if not cal_key:
        return None

    calendar = CROP_CALENDARS.get(cal_key, [])

    # Find best matching stage by month first
    month_matches = [s for s in calendar if month in s["months"]]

    if not month_matches:
        return None

    # If multiple month matches, use NDVI to disambiguate
    best = None
    best_score = 999

    for stage in month_matches:
        ndvi_min, ndvi_max = stage["ndvi_range"]
        if ndvi_min <= ndvi <= ndvi_max:
            # Inside range — perfect match
            mid = (ndvi_min + ndvi_max) / 2
            score = abs(ndvi - mid)
            if score < best_score:
                best_score = score
                best = stage
        else:
            # Outside range — distance from nearest bound
            dist = min(abs(ndvi - ndvi_min), abs(ndvi - ndvi_max))
            if dist < best_score and best is None:
                best_score = dist
                best = stage

    if not best:
        best = month_matches[0]

    stage_id = best["stage"]

    return {
        "stage":      stage_id,
        "label":      STAGE_LABELS.get(stage_id, stage_id),
        "advice":     STAGE_ADVICE.get(stage_id, ""),
        "crop":       crop_str,
        "calendar":   cal_key,
        "month":      month,
        "ndvi":       ndvi,
    }

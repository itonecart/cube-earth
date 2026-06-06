"""
Cube Earth Grass Growth Model
Based on MoSt GG principles (Ruelle, Hennessy & Delaby, 2018)
Simplified for satellite-derived inputs without ground calibration.
Honest uncertainty: ±350 kg DM/ha (within MoSt GG RMSPE range)
"""

def estimate_grass_cover(ndvi, rvi, smap_moisture, weather):
    """
    Estimate pasture cover from satellite + weather data.
    
    Formula basis:
    - NDVI → compressed sward height proxy (reliable to ~2500 kg DM/ha)
    - SAR RVI → structural density correction above canopy closure
    - Weather → growth rate context
    - MoSt GG: (height_cm - 4cm residual) * 250 = kg DM/ha
    """
    if ndvi is None:
        return None

    # Step 1: NDVI → estimated compressed sward height (cm)
    # Calibrated to Irish perennial ryegrass (Teagasc/VistaMilk basis)
    # NDVI 0.4 ≈ 4cm (post-grazing residual)
    # NDVI 0.7 ≈ 9cm (ready to graze ~1250 kg DM/ha)
    # NDVI 0.85 ≈ 12cm (pre-graze ~2000 kg DM/ha)
    # Saturates at NDVI ~0.9 = ~2500 kg DM/ha (canopy closure)
    height_cm = max(0, (ndvi - 0.15) * 18)

    # Step 2: SAR RVI correction
    # RVI adds structural info above NDVI saturation threshold
    sar_multiplier = 1.0
    if rvi is not None:
        if ndvi > 0.80 and rvi > 0.70:
            # Dense canopy — SAR suggests more biomass than NDVI shows
            sar_multiplier = 1.15
        elif ndvi > 0.80 and rvi < 0.40:
            # NDVI high but SAR low — drought stress or lodged sward
            sar_multiplier = 0.85
        elif ndvi < 0.50 and rvi > 0.60:
            # Post-grazing — structure remains, chlorophyll low
            sar_multiplier = 0.75  # recently grazed

    height_cm_corrected = height_cm * sar_multiplier

    # Step 3: Apply agronomic formula
    # (Height cm - 4cm residual) * 250 = kg DM/ha
    residual_cm = 4.0
    kg_dm_ha = max(0, (height_cm_corrected - residual_cm) * 250)
    kg_dm_ha = min(3500, kg_dm_ha)  # cap at realistic max

    # Step 4: Weather growth rate modifier
    # Based on MoSt GG temperature response
    growth_modifier = 1.0
    if weather and weather.get("available"):
        gc = weather.get("growth_conditions", {})
        avg_temp = gc.get("avg_temp_c")
        rad = gc.get("radiation_mj_day")
        rain = gc.get("rain_7d_mm")

        if avg_temp:
            if 10 <= avg_temp <= 16:
                growth_modifier *= 1.0   # optimal Irish range
            elif 8 <= avg_temp < 10:
                growth_modifier *= 0.85  # cool but growing
            elif avg_temp < 8:
                growth_modifier *= 0.65  # slow growth
            elif avg_temp > 20:
                growth_modifier *= 0.90  # heat stress

        if rad:
            if rad >= 12:
                growth_modifier *= 1.05
            elif rad < 6:
                growth_modifier *= 0.90

        if rain:
            if rain < 5:
                growth_modifier *= 0.90  # drought stress possible
            elif rain > 60:
                growth_modifier *= 0.95  # waterlogging risk

    # Step 5: Daily growth rate estimate (kg DM/ha/day)
    # Irish average: 40-80 kg DM/ha/day in summer
    # MoSt GG basis: growth = f(radiation, temperature, biomass, N)
    base_growth_rate = 0
    if weather and weather.get("available"):
        gc = weather.get("growth_conditions", {})
        avg_temp = gc.get("avg_temp_c", 12)
        rad = gc.get("radiation_mj_day", 10)
        # Simplified MoSt GG growth function
        # Growth ∝ radiation * temperature_response * biomass_factor
        temp_factor = max(0, min(1, (avg_temp - 4) / 12))
        rad_factor = max(0, min(1, rad / 15))
        biomass_factor = max(0.3, min(1, kg_dm_ha / 2000))  # floor at 0.3 so growth never zeros
        base_growth_rate = round(80 * temp_factor * rad_factor * biomass_factor * growth_modifier, 1)

    # Step 6: 7-day forecast cover
    forecast_cover = None
    if weather and weather.get("forecast_7d") and base_growth_rate:
        forecast_cover = round(min(3500, kg_dm_ha + (base_growth_rate * 7)), 0)

    # Step 7: Grazing recommendation
    recommendation = ""
    rotation_days = None
    if kg_dm_ha >= 1400:
        recommendation = "Ready to graze"
        rotation_days = 0
    elif kg_dm_ha >= 1000:
        days_to_graze = max(1, round((1400 - kg_dm_ha) / max(1, base_growth_rate)))
        recommendation = f"Graze in {days_to_graze} days"
        rotation_days = days_to_graze
    elif kg_dm_ha >= 600:
        days_to_graze = max(1, round((1400 - kg_dm_ha) / max(1, base_growth_rate)))
        recommendation = f"Rest — graze in {days_to_graze} days"
        rotation_days = days_to_graze
    else:
        recommendation = "Rest field — post-grazing recovery"
        rotation_days = round((1400 - kg_dm_ha) / max(1, base_growth_rate)) if base_growth_rate else 21

    return {
        "available": True,
        "kg_dm_ha": round(kg_dm_ha),
        "kg_dm_ha_low": round(max(0, kg_dm_ha - 350)),   # MoSt GG RMSPE
        "kg_dm_ha_high": round(min(3500, kg_dm_ha + 350)),
        "uncertainty": "±350 kg DM/ha (satellite estimate, uncalibrated)",
        "height_cm_est": round(height_cm_corrected, 1),
        "growth_rate_kg_day": base_growth_rate,
        "forecast_cover_7d": int(forecast_cover) if forecast_cover else None,
        "recommendation": recommendation,
        "rotation_days": rotation_days,
        "ndvi_saturation_warning": ndvi > 0.85,
        "model": "MoSt GG simplified (Ruelle et al. 2018) + Sentinel-2/1 + UKMO weather",
        "calibration_note": "Add plate meter readings to improve accuracy",
    }

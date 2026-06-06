import requests

def get_weather_data(lat, lng):
    """
    Fetch weather data from Open-Meteo for Irish farms.
    Uses UKMO UKV 2km model — best coverage for Ireland.
    Returns current conditions + 7-day forecast + past 7 days.
    No API key required.
    """
    try:
        # Forecast + recent history
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lng,
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "shortwave_radiation_sum",  # MJ/m² — key MoSt GG input
                "et0_fao_evapotranspiration",
                "sunshine_duration",
            ],
            "current": [
                "temperature_2m",
                "precipitation",
                "rain",
                "soil_temperature_0cm",
                "soil_moisture_0_to_1cm",
            ],
            "timezone": "Europe/Dublin",
            "past_days": 7,
            "forecast_days": 7,
            "models": "ukmo_seamless"  # UK Met Office — best for Ireland
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        daily = data.get("daily", {})
        current = data.get("current", {})

        # Calculate key growth indicators
        temps = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        radiation = daily.get("shortwave_radiation_sum", [])
        rain = daily.get("precipitation_sum", [])
        times = daily.get("time", [])

        # Mean temp for past 7 days (growth relevant)
        past_temps = [(temps[i] + temp_min[i]) / 2 for i in range(7) if i < len(temps)]
        avg_temp_7d = round(sum(past_temps) / len(past_temps), 1) if past_temps else None

        # Total radiation past 7 days (MJ/m²)
        past_radiation = radiation[:7]
        total_rad_7d = round(sum(r for r in past_radiation if r), 1)

        # Total rain past 7 days
        past_rain = rain[:7]
        total_rain_7d = round(sum(r for r in past_rain if r), 1)

        # 7-day forecast
        forecast = []
        for i in range(7, min(14, len(times))):
            forecast.append({
                "date": times[i],
                "temp_max": temps[i] if i < len(temps) else None,
                "temp_min": temp_min[i] if i < len(temp_min) else None,
                "rain_mm": rain[i] if i < len(rain) else None,
                "radiation_mj": radiation[i] if i < len(radiation) else None,
            })

        # Simple grass growth index (0-10)
        # Based on MoSt GG principles: temp 8-18°C optimal, radiation >8 MJ/m²/day
        growth_score = 0
        if avg_temp_7d:
            if 8 <= avg_temp_7d <= 18:
                growth_score += 5
            elif 5 <= avg_temp_7d < 8 or 18 < avg_temp_7d <= 22:
                growth_score += 3
            else:
                growth_score += 1
        if total_rad_7d:
            daily_rad = total_rad_7d / 7
            if daily_rad >= 12:
                growth_score += 3
            elif daily_rad >= 8:
                growth_score += 2
            else:
                growth_score += 1
        if total_rain_7d:
            if 10 <= total_rain_7d <= 40:
                growth_score += 2
            elif total_rain_7d > 40:
                growth_score += 1
            else:
                growth_score += 1

        growth_label = (
            "Excellent" if growth_score >= 9 else
            "Good" if growth_score >= 7 else
            "Moderate" if growth_score >= 5 else
            "Poor"
        )

        return {
            "available": True,
            "source": "Open-Meteo UKMO UKV 2km",
            "current": {
                "temp_c": current.get("temperature_2m"),
                "rain_mm": current.get("rain"),
                "soil_temp_c": current.get("soil_temperature_0cm"),
            },
            "past_7d": {
                "avg_temp_c": avg_temp_7d,
                "total_rain_mm": total_rain_7d,
                "total_radiation_mj": total_rad_7d,
            },
            "growth_conditions": {
                "score": growth_score,
                "label": growth_label,
                "avg_temp_c": avg_temp_7d,
                "radiation_mj_day": round(total_rad_7d / 7, 1) if total_rad_7d else None,
                "rain_7d_mm": total_rain_7d,
            },
            "forecast_7d": forecast,
        }

    except Exception as e:
        return {"available": False, "error": str(e)}

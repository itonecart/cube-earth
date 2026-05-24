import asyncio
from datetime import datetime, timezone
from extractors.era5_extractor import ERA5Extractor
from extractors.nasadem_extractor import NASADEMExtractor
from parcel.lpis import LPISClient
from parcel.geometry import parcel_size_class, confidence_penalty
from analytics.soil_moisture import (
    classify_surface, classify_rootzone,
    classify_drainage, n_mineralisation_risk
)
from analytics.drought import drought_stress_index, waterlogging_probability
from analytics.grazing import (
    grazing_suitability, machinery_trafficability, slurry_suitability
)


class ProfileBuilder:

    def __init__(self):
        self.era5    = ERA5Extractor()
        self.nasadem = NASADEMExtractor()
        self.lpis    = LPISClient()

    async def build(self, lat, lng, year):
        start = f"{year}-04-01"
        end   = f"{year}-10-31"

        era5_raw, dem_raw, parcel, commonage = await asyncio.gather(
            self.era5.extract(lat, lng, start, end),
            self.nasadem.extract(lat, lng),
            self.lpis.get_parcel(lat, lng),
            self.lpis.get_commonage(lat, lng),
            return_exceptions=True,
        )

        era5 = self.era5.parse(
            era5_raw if not isinstance(era5_raw, Exception) else None
        )
        dem = self.nasadem.parse(
            dem_raw if not isinstance(dem_raw, Exception) else None
        )

        surf = era5.get("surface_mean")
        root = era5.get("rootzone_mean")
        slope = dem.get("slope_deg") if dem.get("available") else None
        area_ha = parcel.get("claim_area") if parcel else None
        size_class = parcel_size_class(area_ha)
        penalty = confidence_penalty(size_class)

        drainage = classify_drainage(surf, slope)
        drought = drought_stress_index(surf, root)
        waterlog = waterlogging_probability(surf, root, slope)
        grazing = grazing_suitability(surf, slope, waterlog["probability"], area_ha)
        traffic = machinery_trafficability(surf, root, slope)
        slurry = slurry_suitability(surf, slope, traffic["score"])

        return {
            "location": {"lat": lat, "lng": lng},
            "year": year,
            "parcel": parcel,
            "commonage": commonage,
            "terrain": dem,
            "soil_moisture": {
                **era5,
                "surface_status":  classify_surface(surf),
                "rootzone_status": classify_rootzone(root),
                "drainage_class":  drainage,
                "n_mineralisation": n_mineralisation_risk(surf),
            },
            "stress": {
                "drought":     drought,
                "waterlogging": waterlog,
            },
            "agronomic": {
                "grazing_suitability":      grazing,
                "machinery_trafficability": traffic,
                "slurry_spreading":         slurry,
            },
            "parcel_context": {
                "size_class":         size_class,
                "area_ha":            area_ha,
                "confidence_penalty": penalty,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


builder = ProfileBuilder()

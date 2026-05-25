import asyncio
from datetime import datetime, timezone
from extractors.era5_extractor import ERA5Extractor
from extractors.nasadem_extractor import NASADEMExtractor
from extractors.hls_extractor import HLSExtractor
from parsers.hls_parser import compute_indices
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


def interpret_ndvi(v):
    if v is None: return "No data"
    if v > 0.80: return "Excellent grass cover"
    if v > 0.65: return "Good grass cover"
    if v > 0.50: return "Moderate grass cover"
    if v > 0.35: return "Low grass cover"
    return "Poor or bare"

def interpret_gcap(v):
    if v is None: return "No data"
    if v > 0.60: return "Strong sward density"
    if v > 0.45: return "Moderate sward density"
    if v > 0.30: return "Low-moderate sward"
    return "Weak sward"


class ProfileBuilder:

    def __init__(self):
        self.era5    = ERA5Extractor()
        self.nasadem = NASADEMExtractor()
        self.hls     = HLSExtractor()
        self.lpis    = LPISClient()

    async def build(self, lat, lng, year):
        start = f"{year}-04-01"
        end   = f"{year}-10-31"

        era5_raw, dem_raw, parcel, commonage, hls_raw = await asyncio.gather(
            self.era5.extract(lat, lng, start, end),
            self.nasadem.extract(lat, lng),
            self.lpis.get_parcel(lat, lng),
            self.lpis.get_commonage(lat, lng),
            self.hls.extract(lat, lng, start, end),
            return_exceptions=True,
        )

        era5 = self.era5.parse(
            era5_raw if not isinstance(era5_raw, Exception) else None
        )
        dem = self.nasadem.parse(
            dem_raw if not isinstance(dem_raw, Exception) else None
        )
        hls_result = self.hls.parse(
            hls_raw if not isinstance(hls_raw, Exception) else None
        )

        # Get vegetation indices from best granule
        indices = None
        best_granule = hls_result.get("latest")
        if best_granule and hls_result.get("available"):
            try:
                indices = await compute_indices(best_granule, lat, lng)
            except Exception:
                indices = None

        surf  = era5.get("surface_mean")
        root  = era5.get("rootzone_mean")
        slope = dem.get("slope_deg") if dem.get("available") else None
        area_ha    = parcel.get("claim_area") if parcel else None
        size_class = parcel_size_class(area_ha)
        penalty    = confidence_penalty(size_class)

        ndvi = indices.get("ndvi") if indices else None
        ndre = indices.get("ndre") if indices else None
        gcap = indices.get("gcap") if indices else None

        drainage = classify_drainage(surf, slope)
        drought  = drought_stress_index(surf, root)
        waterlog = waterlogging_probability(surf, root, slope)
        grazing  = grazing_suitability(surf, slope, waterlog["probability"], area_ha)
        traffic  = machinery_trafficability(surf, root, slope)
        slurry   = slurry_suitability(surf, slope, traffic["score"])

        return {
            "location": {"lat": lat, "lng": lng},
            "year":     year,
            "parcel":   parcel,
            "commonage": commonage,
            "terrain":  dem,
            "vegetation": {
                "available":   indices is not None,
                "ndvi":        ndvi,
                "ndre":        ndre,
                "cire":        indices.get("cire") if indices else None,
                "gcap":        gcap,
                "ndvi_status": interpret_ndvi(ndvi),
                "gcap_status": interpret_gcap(gcap),
                "granule_date": best_granule.get("time_start") if best_granule else None,
                "cloud_cover":  best_granule.get("cloud_cover") if best_granule else None,
                "source":       "HLS Sentinel-2 30m",
            },
            "soil_moisture": {
                **era5,
                "surface_status":   classify_surface(surf),
                "rootzone_status":  classify_rootzone(root),
                "drainage_class":   drainage,
                "n_mineralisation": n_mineralisation_risk(surf),
            },
            "stress": {
                "drought":      drought,
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

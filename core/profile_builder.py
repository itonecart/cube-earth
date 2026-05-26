import asyncio
from datetime import datetime, timezone
from extractors.era5_extractor import ERA5Extractor
from extractors.nasadem_extractor import NASADEMExtractor
from extractors.hls_extractor import HLSExtractor
from extractors.sentinel1_extractor import Sentinel1Extractor
from extractors.smap_extractor import SMAPExtractor
from extractors.ecostress_extractor import ECOSTRESSExtractor
from parsers.hls_parser import compute_indices
from parsers.sar_parser import extract_s1_backscatter
from parsers.ecostress_parser import extract_lst
from parcel.lpis import LPISClient
from parcel.geometry import parcel_size_class, confidence_penalty
from analytics.soil_moisture import classify_surface, classify_rootzone, classify_drainage, n_mineralisation_risk
from analytics.drought import drought_stress_index, waterlogging_probability
from analytics.grazing import grazing_suitability, machinery_trafficability, slurry_suitability
from analytics.crop_classifier import classify_crop, ndvi_status_for_crop
from analytics.tillage import tillage_decisions
from core.confidence_engine import (
    s2_confidence, smap_confidence, era5_confidence,
    s1_confidence, ecostress_confidence, parcel_confidence,
    cross_sensor_agreement, freshness_summary,
    explainability, overall_confidence,
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

def fuse_moisture(smap_surf, era5_surf, smap_root, era5_root):
    def fuse(sat, model, sat_w=0.60, model_w=0.40):
        if sat is None and model is None: return None
        if sat is None: return model
        if model is None: return sat
        return round(sat * sat_w + model * model_w, 4)
    return {
        "surface_fused":  fuse(smap_surf, era5_surf),
        "rootzone_fused": fuse(smap_root, era5_root),
        "method": "SMAP(60%) + ERA5(40%)",
    }


class ProfileBuilder:

    def __init__(self):
        self.era5      = ERA5Extractor()
        self.nasadem   = NASADEMExtractor()
        self.hls       = HLSExtractor()
        self.sentinel1 = Sentinel1Extractor()
        self.smap      = SMAPExtractor()
        self.ecostress = ECOSTRESSExtractor()
        self.lpis      = LPISClient()

    async def build(self, lat, lng, year):
        start = f"{year}-04-01"
        end   = f"{year}-10-31"

        # Run all extractors in parallel
        results = await asyncio.gather(
            self.era5.extract(lat, lng, start, end),
            self.nasadem.extract(lat, lng),
            self.lpis.get_parcel(lat, lng),
            self.lpis.get_commonage(lat, lng),
            self.hls.extract(lat, lng, start, end),
            self.sentinel1.extract(lat, lng, start, end),
            self.smap.extract(lat, lng, start, end),
            return_exceptions=True,
        )
        era5_raw, dem_raw, parcel, commonage, hls_raw, s1_raw, smap_raw = results

        era5       = self.era5.parse(era5_raw if not isinstance(era5_raw, Exception) else None)
        dem        = self.nasadem.parse(dem_raw if not isinstance(dem_raw, Exception) else None)
        hls_result = self.hls.parse(hls_raw if not isinstance(hls_raw, Exception) else None)
        s1_result  = self.sentinel1.parse(s1_raw if not isinstance(s1_raw, Exception) else None)
        smap_result= self.smap.parse(smap_raw if not isinstance(smap_raw, Exception) else None)

        # Run pixel extractions in parallel
        best = hls_result.get("latest")
        eco_raw = await self.ecostress.extract(lat, lng, start, end)
        sar_result  = await extract_s1_backscatter(lat, lng, start, end)
        eco_result = self.ecostress.parse(eco_raw)

        indices = None
        if best and hls_result.get("available"):
            try:
                indices = await compute_indices(best, lat, lng)
            except Exception:
                indices = None

        lst = eco_result if eco_result.get("available") else None

        surf  = era5.get("surface_mean")
        root  = era5.get("rootzone_mean")
        slope = dem.get("slope_deg") if dem.get("available") else None
        area_ha    = parcel.get("claim_area") if parcel else None
        size_class = parcel_size_class(area_ha)
        penalty    = confidence_penalty(size_class)
        ndvi = indices.get("ndvi") if indices else None
        gcap = indices.get("gcap") if indices else None
        crop_str   = parcel.get("crop") if parcel else None
        crop_info  = classify_crop(crop_str)
        crop_class = crop_info["class"]

        smap_surf = smap_result.get("sm_surface_m3") if smap_result.get("available") else None
        smap_root = smap_result.get("sm_rootzone_m3") if smap_result.get("available") else None
        fusion    = fuse_moisture(smap_surf, surf, smap_root, root)

        surf_use = fusion["surface_fused"] or surf
        root_use = fusion["rootzone_fused"] or root

        drainage = classify_drainage(surf_use, slope)
        drought  = drought_stress_index(surf_use, root_use)
        waterlog = waterlogging_probability(surf_use, root_use, slope)
        traffic  = machinery_trafficability(surf_use, root_use, slope)
        slurry   = slurry_suitability(surf_use, slope, traffic["score"])

        # Crop-aware decisions
        if crop_class == "grassland" or crop_info.get("grazing_relevant"):
            grazing  = grazing_suitability(surf_use, slope, waterlog["probability"], area_ha, ndvi=ndvi, crop=crop_str)
            tillage_intel = None
        else:
            grazing = None
            ndvi_age = None
            if best:
                from datetime import datetime, timezone
                try:
                    ts = best.get("time_start","")
                    if ts:
                        t = datetime.fromisoformat(ts.replace("Z","+00:00"))
                        ndvi_age = (datetime.now(timezone.utc) - t).days
                except Exception:
                    pass
            tillage_intel = tillage_decisions(ndvi, ndvi_age, surf_use, root_use, slope, crop_str, traffic["score"])

        # Confidence engine
        s2c     = s2_confidence(
                      ndvi,
                      indices.get("ndre") if indices else None,
                      best.get("cloud_cover") if best else 100,
                      best.get("time_start") if best else None)
        smapc   = smap_confidence(
                      smap_surf, smap_root,
                      smap_result.get("granule_date") if smap_result.get("available") else None)
        era5c   = era5_confidence(surf, era5.get("obs_count"))
        s1c     = s1_confidence(
                      s1_result.get("granule_count"),
                      s1_result.get("latest", {}).get("time_start") if s1_result.get("latest") else None,
                      sar_extracted=sar_result.get("available") if sar_result else False)
        ecoc    = ecostress_confidence(
                      lst.get("celsius") if lst else None,
                      lst.get("granule_time") if lst else None)
        parcelc = parcel_confidence(area_ha, parcel.get("crop") if parcel else None)
        agree   = cross_sensor_agreement(
                      ndvi, smap_surf, surf,
                      s1_result.get("granule_count"),
                      rvi=sar_result.get("rvi") if sar_result else None,
                      vv_db=sar_result.get("vv_db") if sar_result else None,
                      vh_db=sar_result.get("vh_db") if sar_result else None,
                      s2_age=s2c.get("age_days"),
                      ecostress_available=lst is not None and lst.get("available", False))
        fresh   = freshness_summary(
                      best.get("time_start") if best else None,
                      smap_result.get("granule_date") if smap_result.get("available") else None,
                      s1_result.get("latest", {}).get("time_start") if s1_result.get("latest") else None,
                      lst.get("granule_time") if lst else None,
                      sar_latest=sar_result.get("latest_acquisition") if sar_result else None,
                      sar_acquisitions=sar_result.get("acquisitions") if sar_result else None)
        explain = explainability(
                      grazing, traffic, slurry, drought, waterlog,
                      ndvi, gcap, surf_use, root_use, slope, drainage,
                      s2_age=s2c.get("age_days"),
                      smap_age=smapc.get("age_days"),
                      era5_age=None)
        conf    = overall_confidence(s2c, smapc, era5c, s1c, ecoc, parcelc, agree)

        return {
            "location":  {"lat": lat, "lng": lng},
            "year":      year,
            "parcel":    parcel,
            "commonage": commonage,
            "terrain":   dem,
            "vegetation": {
                "available":    indices is not None,
                "ndvi":         ndvi,
                "ndre":         indices.get("ndre") if indices else None,
                "cire":         indices.get("cire") if indices else None,
                "gcap":         gcap,
                "ndvi_status":  ndvi_status_for_crop(ndvi, crop_class),
                "gcap_status":  interpret_gcap(gcap),
                "granule_date": best.get("time_start") if best else None,
                "cloud_cover":  best.get("cloud_cover") if best else None,
                "source":       "HLS Sentinel-2 30m",
            },
            "thermal": lst if lst and lst.get("available") else {
                "available": False,
                "source": "ECOSTRESS",
            },
            "sar": {
                "available":        sar_result.get("available") if sar_result else False,
                "vv_db":            sar_result.get("vv_db") if sar_result else None,
                "vh_db":            sar_result.get("vh_db") if sar_result else None,
                "rvi":              sar_result.get("rvi") if sar_result else None,
                "rvi_interpretation": sar_result.get("rvi_interpretation") if sar_result else None,
                "canopy_wetness":   sar_result.get("canopy_wetness") if sar_result else None,
                "acquisitions":     sar_result.get("acquisitions") if sar_result else None,
                "calibration":      sar_result.get("calibration") if sar_result else None,
                "speckle_filter":   sar_result.get("speckle_filter") if sar_result else None,
                "granule_count":    s1_result.get("granule_count"),
                "source":           sar_result.get("source") if sar_result else s1_result.get("source"),
                "note":             sar_result.get("note") if sar_result else None,
            },
            "soil_moisture": {
                "smap": smap_result,
                "era5": {
                    **era5,
                    "surface_status":  classify_surface(surf),
                    "rootzone_status": classify_rootzone(root),
                },
                "fused": {
                    **fusion,
                    "surface_status":   classify_surface(surf_use),
                    "rootzone_status":  classify_rootzone(root_use),
                    "drainage_class":   drainage,
                    "n_mineralisation": n_mineralisation_risk(surf_use),
                },
            },
            "stress": {
                "drought":      drought,
                "waterlogging": waterlog,
            },
            "agronomic": {
                "crop_class":               crop_class,
                "crop_info":                crop_info,
                "grazing_suitability":      grazing,
                "tillage_intelligence":     tillage_intel,
                "machinery_trafficability": traffic,
                "slurry_spreading":         slurry,
            },
            "parcel_context": {
                "size_class":         size_class,
                "area_ha":            area_ha,
                "confidence_penalty": penalty,
            },
            "confidence":    conf,
            "freshness":     fresh,
            "agreement":     agree,
            "explainability": explain,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


builder = ProfileBuilder()

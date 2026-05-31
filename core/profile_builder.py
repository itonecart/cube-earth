import asyncio
from datetime import datetime, timezone
from extractors.era5_extractor import ERA5Extractor
from extractors.gee_extractor import GEEExtractor
from extractors.gee_optical_extractor import GEEOpticalExtractor
from extractors.gee_seasonal_extractor import GEESeasonalExtractor
from extractors.gee_sar_extractor import GEESARExtractor
from extractors.gee_thermal_extractor import GEEThermalExtractor
from extractors.gee_modis_extractor import GEEMODISExtractor
from extractors.nasadem_extractor import NASADEMExtractor
from extractors.hls_extractor import HLSExtractor
from extractors.sentinel1_extractor import Sentinel1Extractor
from extractors.smap_extractor import SMAPExtractor
from extractors.ecostress_extractor import ECOSTRESSExtractor
from parsers.hls_parser import compute_indices
from parsers.sar_parser import extract_s1_backscatter
from parsers.ecostress_parser import extract_lst
from parcel.lpis import LPISClient
from parcel.dafm_api import get_parcel_at_point
from parcel.geometry import parcel_size_class, confidence_penalty
from analytics.soil_moisture import classify_surface, classify_rootzone, classify_drainage, n_mineralisation_risk
from analytics.drought import drought_stress_index, waterlogging_probability
from analytics.grazing import grazing_suitability, machinery_trafficability, slurry_suitability
from analytics.crop_classifier import classify_crop, ndvi_status_for_crop
from analytics.crop_stage import detect_crop_stage
from analytics.trend_interpreter import interpret_trend
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
        self.gee       = GEEExtractor()
        self.gee_optical = GEEOpticalExtractor()
        self.gee_seasonal = GEESeasonalExtractor()
        self.gee_sar     = GEESARExtractor()
        self.gee_thermal = GEEThermalExtractor()
        self.gee_modis   = GEEMODISExtractor()
        self.nasadem   = NASADEMExtractor()
        self.hls       = HLSExtractor()
        self.sentinel1 = Sentinel1Extractor()
        self.smap      = SMAPExtractor()
        self.ecostress = ECOSTRESSExtractor()
        self.lpis      = LPISClient()

    async def build(self, lat, lng, year, parcel_override=None):
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
        era5_raw, dem_raw, parcel_supabase, commonage, hls_raw, s1_raw, smap_raw = results

        # Use parcel_override if provided (from UI selection)
        if parcel_override and parcel_override.get("crop"):
            dafm_parcel = {**parcel_override, "_source": "UI selection", "_match_distance_m": 0, "_match_quality": "exact"}
            print(f"Using UI parcel override: {parcel_override.get('crop')} {parcel_override.get('claim_area')}ha")
            # Use parcel centroid for GEE extraction if geometry provided
            geom = parcel_override.get("geometry")
            if geom and geom.get("type") == "Polygon":
                coords = geom.get("coordinates", [[]])[0]
                if coords:
                    lng = sum(c[0] for c in coords) / len(coords)
                    lat = sum(c[1] for c in coords) / len(coords)
        else:
            # Try DAFM GeoAPI first — exact point-in-polygon
            try:
                dafm_parcel = await get_parcel_at_point(lat, lng)
                if dafm_parcel:
                    print(f"DAFM API: {dafm_parcel.get('crop')} at {dafm_parcel.get('_match_distance_m')}m")
                else:
                    print("DAFM API: no parcel found — falling back to Supabase")
            except Exception as _de:
                print(f"DAFM API error: {_de}")
                dafm_parcel = None

        # Use DAFM only — Supabase had only 50k parcels, DAFM has full Ireland
        parcel = dafm_parcel if dafm_parcel else {}

        era5       = self.era5.parse(era5_raw if not isinstance(era5_raw, Exception) else None)
        dem        = self.nasadem.parse(dem_raw if not isinstance(dem_raw, Exception) else None)
        hls_result = self.hls.parse(hls_raw if not isinstance(hls_raw, Exception) else None)
        s1_result  = self.sentinel1.parse(s1_raw if not isinstance(s1_raw, Exception) else None)
        smap_result= self.smap.parse(smap_raw if not isinstance(smap_raw, Exception) else None)

        # Run pixel extractions in parallel
        best = hls_result.get("latest")

        # GEE Optical — primary current NDVI (fresher than HLS)
        try:
            import concurrent.futures
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = loop.run_in_executor(
                    pool,
                    lambda: asyncio.run(self.gee_optical.extract(lat, lng))
                )
                gee_optical_raw = await asyncio.wait_for(future, timeout=15)
        except Exception as _goe:
            gee_optical_raw = {"available": False, "error": str(_goe)}

        gee_optical = self.gee_optical.parse(gee_optical_raw)

        # Seasonal anomaly — run in background with timeout
        gee_seasonal_raw = {"available": False}
        try:
            import concurrent.futures
            loop = asyncio.get_event_loop()
            _current_ndvi = gee_optical.get("ndvi")
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = loop.run_in_executor(
                    pool,
                    lambda: asyncio.run(self.gee_seasonal.extract(lat, lng, _current_ndvi))
                )
                gee_seasonal_raw = await asyncio.wait_for(future, timeout=12)
        except Exception as _gs:
            gee_seasonal_raw = {"available": False, "error": str(_gs)}
        # Parse seasonal after ndvi is unified below
        gee_seasonal_raw_stored = gee_seasonal_raw

        # GEE SAR — replaces CDSE
        gee_sar_raw = {"available": False}
        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = loop.run_in_executor(
                    pool, lambda: asyncio.run(self.gee_sar.extract(lat, lng))
                )
                gee_sar_raw = await asyncio.wait_for(future, timeout=12)
        except Exception as _gs:
            gee_sar_raw = {"available": False, "error": str(_gs)}
        gee_sar = self.gee_sar.parse(gee_sar_raw)

        # GEE Thermal — Landsat fallback for ECOSTRESS
        gee_thermal_raw = {"available": False}
        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = loop.run_in_executor(
                    pool, lambda: asyncio.run(self.gee_thermal.extract(lat, lng))
                )
                gee_thermal_raw = await asyncio.wait_for(future, timeout=30)
        except Exception as _gt:
            gee_thermal_raw = {"available": False, "error": str(_gt)}
        gee_thermal = self.gee_thermal.parse(gee_thermal_raw)

        # MODIS — daily LST + NDVI history
        gee_modis_raw = {"available": False}
        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = loop.run_in_executor(
                    pool, lambda: asyncio.run(self.gee_modis.extract(lat, lng, days=14))
                )
                gee_modis_raw = await asyncio.wait_for(future, timeout=12)
        except Exception as _gm:
            gee_modis_raw = {"available": False, "error": str(_gm)}
        gee_modis = self.gee_modis.parse(gee_modis_raw)
        eco_raw = await self.ecostress.extract(lat, lng, start, end)
        sar_result  = await extract_s1_backscatter(lat, lng, start, end)
        eco_result = self.ecostress.parse(eco_raw)

        # GEE NDVI time series — optional, memory-safe
        gee_raw = {"available": False, "error": "skipped"}
        try:
            import concurrent.futures, asyncio as _asyncio
            loop = _asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = loop.run_in_executor(
                    pool,
                    lambda: _asyncio.run(self.gee.extract(lat, lng))
                )
                gee_raw = await _asyncio.wait_for(future, timeout=25)
        except Exception as _ge:
            gee_raw = {"available": False, "error": str(_ge)}
        gee_result = self.gee.parse(gee_raw)

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
        # GEE optical as primary — fresher than HLS
        gee_ndvi  = gee_optical.get("ndvi") if gee_optical.get("available") else None
        gee_ndre  = gee_optical.get("ndre") if gee_optical.get("available") else None
        gee_cire  = gee_optical.get("cire") if gee_optical.get("available") else None
        gee_gcap  = gee_optical.get("gcap") if gee_optical.get("available") else None
        gee_age   = gee_optical.get("age_days") if gee_optical.get("available") else None
        hls_ndvi  = indices.get("ndvi") if indices else None
        hls_age   = None
        if best:
            try:
                from datetime import datetime as _dt2, timezone as _tz2
                ts2 = best.get("time_start","")
                if ts2:
                    t2 = _dt2.fromisoformat(ts2.replace("Z","+00:00"))
                    hls_age = (_dt2.now(_tz2.utc) - t2).days
            except Exception:
                pass

        use_gee_optical = (
            gee_ndvi is not None and (
                hls_ndvi is None or
                hls_age is None or
                (gee_age is not None and gee_age <= hls_age)
            )
        )

        if use_gee_optical:
            ndvi          = gee_ndvi
            ndre          = gee_ndre
            cire          = gee_cire
            gcap          = gee_gcap
            optical_source = gee_optical.get("source", "GEE Sentinel-2 SR 10m")
            optical_date   = gee_optical.get("date")
            optical_age    = gee_age
            optical_cloud  = gee_optical.get("cloud_cover", 0)
        else:
            ndvi          = hls_ndvi
            ndre          = indices.get("ndre") if indices else None
            cire          = indices.get("cire") if indices else None
            gcap          = indices.get("gcap") if indices else None
            optical_source = "HLS Sentinel-2 30m"
            optical_date   = best.get("time_start") if best else None
            optical_age    = hls_age
            optical_cloud  = best.get("cloud_cover") if best else None

        # SINGLE OPTICAL AUTHORITY — all downstream uses unified variables
        # ndvi, ndre, cire, gcap, optical_source, optical_date, optical_age, optical_cloud
        # Now parse seasonal with correct ndvi
        gee_seasonal = self.gee_seasonal.parse(gee_seasonal_raw_stored, current_ndvi=ndvi)

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
        # Slurry only relevant for grassland/pasture systems
        if crop_class in ("grassland", "unknown") or crop_info.get("grazing_relevant"):
            slurry = slurry_suitability(surf_use, slope, traffic["score"])
        else:
            slurry = None

        # Crop-aware decisions
        if crop_class == "grassland" or crop_info.get("grazing_relevant"):
            grazing  = grazing_suitability(surf_use, slope, waterlog["probability"], area_ha, ndvi=ndvi, crop=crop_str)
            tillage_intel = None
        else:
            grazing = None
            # Use optical_age (GEE or HLS whichever is primary)
            ndvi_age = optical_age
            tillage_intel = tillage_decisions(ndvi, ndvi_age, surf_use, root_use, slope, crop_str, traffic["score"])

        # Confidence engine
        s2c     = s2_confidence(
                      ndvi,
                      ndre,
                      optical_cloud or 0,
                      optical_date)
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
                      lst.get("granule_time") if lst else None,
                      landsat_lst=gee_thermal.get("lst_celsius") if gee_thermal.get("available") else None,
                      landsat_age=gee_thermal.get("age_days") if gee_thermal.get("available") else None)
        match_dist = parcel.get("_match_distance_m") if parcel else None
        match_qual = parcel.get("_match_quality") if parcel else None
        parcelc = parcel_confidence(area_ha, parcel.get("crop") if parcel else None, match_dist, match_qual)
        agree   = cross_sensor_agreement(
                      ndvi, smap_surf, surf,
                      s1_result.get("granule_count"),
                      rvi=sar_result.get("rvi") if sar_result else None,
                      vv_db=sar_result.get("vv_db") if sar_result else None,
                      vh_db=sar_result.get("vh_db") if sar_result else None,
                      s2_age=s2c.get("age_days"),
                      ecostress_available=(lst is not None and lst.get("available", False)) or gee_thermal.get("available", False))
        # Use Landsat thermal date if ECOSTRESS unavailable
        # Only use ECOSTRESS date if actually available
        thermal_date = lst.get("granule_time") if lst and lst.get("available") else None
        # Add Landsat to freshness if available
        landsat_freshness_date = gee_thermal.get("latest_date") if gee_thermal.get("available") else None
        landsat_age = gee_thermal.get("age_days") if gee_thermal.get("available") else None

        fresh   = freshness_summary(
                      optical_date if use_gee_optical else (best.get("time_start") if best else None),
                      smap_result.get("granule_date") if smap_result.get("available") else None,
                      s1_result.get("latest", {}).get("time_start") if s1_result.get("latest") else None,
                      thermal_date,
                      landsat_date=landsat_freshness_date,
                      landsat_age_days=landsat_age,
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
                "ndre":         ndre,
                "cire":         cire,
                "gcap":         gcap,
                "ndvi_status":  ndvi_status_for_crop(ndvi, crop_class),
                "gcap_status":  interpret_gcap(gcap),
                "granule_date": optical_date,
                "cloud_cover":  optical_cloud,
                "age_days":     optical_age,
                "source":       optical_source,
                "gee_optical":  gee_optical.get("available", False),
            },
            "vegetation_trend": {
                "available":    gee_result.get("available", False),
                "trend_arrow":  gee_result.get("trend_arrow"),
                "trend_label":  gee_result.get("trend_label"),
                "short_trend":  gee_result.get("short_trend"),
                "long_trend":   gee_result.get("long_trend"),
                "short_diff":   gee_result.get("short_diff"),
                "long_diff":    gee_result.get("long_diff"),
                "trend_7d":     gee_result.get("trend_7d"),
                "diff_7d":      gee_result.get("diff_7d"),
                "trend_30d":    gee_result.get("trend_30d"),
                "diff_30d":     gee_result.get("diff_30d"),
                "latest_ndvi":  gee_result.get("latest", {}).get("ndvi") if gee_result.get("latest") else None,
                "latest_date":  gee_result.get("latest", {}).get("date") if gee_result.get("latest") else None,
                "series":       gee_result.get("series", []),
                "count":        gee_result.get("count", 0),
                "parcel_mismatch": (
                    parcel is not None and
                    parcel.get("grassland") and
                    gee_result.get("latest", {}).get("ndvi", 1) is not None and
                    gee_result.get("latest", {}).get("ndvi", 1) < 0.25
                ),
                "source":       "GEE Sentinel-2 SR 10m",
                "events":       gee_result.get("events", []),
                "interpretation": interpret_trend(
                    gee_result.get("long_trend"),
                    gee_result.get("short_trend"),
                    gee_result.get("long_diff"),
                    ndvi,
                    crop_class,
                    anomaly_pct=gee_seasonal.get("anomaly_pct"),
                    events=gee_result.get("events", []),
                ),
                "seasonal": {
                    "available":     gee_seasonal.get("available", False),
                    "baseline_mean": gee_seasonal.get("baseline_mean"),
                    "anomaly_pct":   gee_seasonal.get("anomaly_pct"),
                    "anomaly_label": gee_seasonal.get("anomaly_label"),
                    "anomaly_level": gee_seasonal.get("anomaly_level"),
                    "years_used":    gee_seasonal.get("years_used"),
                    "yearly_ndvi":   gee_seasonal.get("yearly_ndvi", {}),
                },
            },
            "thermal": lst if lst and lst.get("available") else (
                {**gee_thermal, "source": gee_thermal.get("source", "GEE Landsat Thermal"),
                 "lst_celsius": gee_thermal.get("lst_celsius"),
                 "fallback": "landsat"} if gee_thermal.get("available") else {
                "available": False, "source": "ECOSTRESS/Landsat unavailable"}
            ),
            "sar": {
                "available":          gee_sar.get("available") or (sar_result.get("available") if sar_result else False),
                "vv_db":              gee_sar.get("vv_db") or (sar_result.get("vv_db") if sar_result else None),
                "vh_db":              gee_sar.get("vh_db") or (sar_result.get("vh_db") if sar_result else None),
                "rvi":                gee_sar.get("rvi") or (sar_result.get("rvi") if sar_result else None),
                "rvi_interpretation": gee_sar.get("rvi_interpretation") or (sar_result.get("rvi_interpretation") if sar_result else None),
                "canopy_wetness":     sar_result.get("canopy_wetness") if sar_result else None,
                "acquisitions":       gee_sar.get("acquisitions") or (sar_result.get("acquisitions") if sar_result else None),
                "calibration":        gee_sar.get("calibration") or (sar_result.get("calibration") if sar_result else None),
                "speckle_filter":     gee_sar.get("speckle_filter") or (sar_result.get("speckle_filter") if sar_result else None),
                "granule_count":      gee_sar.get("acquisitions") or s1_result.get("granule_count"),
                "source":             gee_sar.get("source") or (sar_result.get("source") if sar_result else None),
                "note":               gee_sar.get("note") or (sar_result.get("note") if sar_result else None),
                "gee_sar":            gee_sar.get("available", False),
            },
            "modis": {
                "available":    gee_modis.get("available", False),
                "lst_celsius":  gee_modis.get("lst_celsius"),
                "lst_date":     gee_modis.get("lst_date"),
                "lst_age_days": gee_modis.get("lst_age_days"),
                "lst_series":   gee_modis.get("lst_series", []),
                "modis_ndvi":   gee_modis.get("modis_ndvi"),
                "modis_ndvi_date": gee_modis.get("modis_ndvi_date"),
                "source":       gee_modis.get("source", "MODIS Terra"),
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
                "crop_stage":               detect_crop_stage(crop_str, ndvi, events=gee_result.get("events", [])),
                "grazing_suitability":      grazing,
                "tillage_intelligence":     tillage_intel,
                "machinery_trafficability": traffic,
                "slurry_spreading":         slurry,
            },
            "parcel_context": {
                "size_class":         size_class,
                "area_ha":            area_ha,
                "confidence_penalty": penalty,
                "match_distance_m":   parcel.get("_match_distance_m") if parcel else None,
                "match_quality":      parcel.get("_match_quality") if parcel else None,
                "match_warning":      (
                    f"Nearest matched parcel {parcel.get('_match_distance_m')}m away — results may reflect nearby field"
                    if parcel and parcel.get("_match_distance_m", 0) > 500 else None
                ),
            },
            "confidence":    conf,
            "freshness":     fresh,
            "agreement":     agree,
            "explainability": explain,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


builder = ProfileBuilder()

import asyncio
from datetime import datetime, timezone
from extractors.smap_extractor import SMAPExtractor
from extractors.era5_extractor import ERA5Extractor
from extractors.nasadem_extractor import NASADEMExtractor
from parcel.lpis import LPISClient
from parcel.geometry import parcel_size_class, confidence_penalty


class ProfileBuilder:

    def __init__(self):
        self.smap    = SMAPExtractor()
        self.era5    = ERA5Extractor()
        self.nasadem = NASADEMExtractor()
        self.lpis    = LPISClient()

    async def build(self, lat, lng, year):
        start = f"{year}-04-01"
        end   = f"{year}-10-31"

        results = await asyncio.gather(
            self.era5.extract(lat, lng, start, end),
            self.nasadem.extract(lat, lng),
            self.lpis.get_parcel(lat, lng),
            self.lpis.get_commonage(lat, lng),
            return_exceptions=True,
        )

        era5_raw, dem_raw, parcel, commonage = results

        era5    = self.era5.parse(
            era5_raw if not isinstance(era5_raw, Exception) else None
        )
        dem     = self.nasadem.parse(
            dem_raw if not isinstance(dem_raw, Exception) else None
        )

        area_ha    = parcel.get("claim_area") if parcel else None
        size_class = parcel_size_class(area_ha)
        penalty    = confidence_penalty(size_class)

        return {
            "location": {"lat": lat, "lng": lng},
            "year":     year,
            "parcel":   parcel,
            "commonage": commonage,
            "terrain":  dem,
            "soil_moisture": era5,
            "parcel_context": {
                "size_class":         size_class,
                "area_ha":            area_ha,
                "confidence_penalty": penalty,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


builder = ProfileBuilder()

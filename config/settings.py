import os
from dotenv import load_dotenv

load_dotenv()

class Settings:

    # NASA Earthdata
    NASA_TOKEN = os.getenv("NASA_EARTHDATA_TOKEN")

    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    # Ireland bounding box
    IRELAND_BBOX = (-10.5, 51.3, -6.0, 55.4)

    # Sensor collections
    SMAP_COLLECTION      = "C3480440870-NSIDC_CPRD"
    ECOSTRESS_COLLECTION = "C2076090826-LPCLOUD"
    HLS_S30_COLLECTION   = "C2021957295-LPCLOUD"
    SENTINEL1_COLLECTION = "C1214470533-ASF"
    NASADEM_COLLECTION   = "C2036882064-LPCLOUD"

    # Cache TTL seconds
    SMAP_TTL      = 43200
    ECOSTRESS_TTL = 604800
    WEATHER_TTL   = 7200

settings = Settings()

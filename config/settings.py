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

    # Sensors
    SMAP_COLLECTION      = "C2208420167-POCLOUD"
    ECOSTRESS_COLLECTION = "C2076090826-LPCLOUD"
    HLS_S30_COLLECTION   = "C2021957295-LPCLOUD"
    PALSAR2_COLLECTION   = "C2777443834-ASF"
    NASADEM_COLLECTION   = "C2036882064-LPCLOUD"

    # Cache TTL seconds
    SMAP_TTL      = 43200   # 12 hours
    ECOSTRESS_TTL = 604800  # 7 days
    WEATHER_TTL   = 7200    # 2 hours

settings = Settings()

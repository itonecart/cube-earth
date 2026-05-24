# Field profile orchestration foundation

class FieldProfileService:

    def __init__(
        self,
        cache,
        extractors,
        quality,
        profile
    ):

        self.cache = cache

        self.extractors = extractors

        self.quality = quality

        self.profile = profile

    async def build_profile(
        self,
        lat,
        lng,
        year
    ):

        raise NotImplementedError

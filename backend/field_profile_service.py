from core.profile_builder import ProfileBuilder


class FieldProfileService:

    def __init__(self):
        self.builder = ProfileBuilder()

    async def build_profile(self, lat, lng, year):
        if not (51.3 <= lat <= 55.4):
            raise ValueError(f"Latitude {lat} outside Ireland")
        if not (-10.5 <= lng <= -6.0):
            raise ValueError(f"Longitude {lng} outside Ireland")
        return await self.builder.build(lat, lng, year)


service = FieldProfileService()

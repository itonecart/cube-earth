# Base extractor foundation

class BaseExtractor:

    def __init__(
        self,
        sensor_name
    ):

        self.sensor_name = sensor_name

    async def search(
        self,
        lat,
        lng,
        start_date,
        end_date
    ):

        raise NotImplementedError

    async def extract(
        self,
        granule,
        geometry
    ):

        raise NotImplementedError

    async def quality(
        self,
        result
    ):

        raise NotImplementedError

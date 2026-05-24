# Granule discovery foundation

class GranuleSearch:

    def __init__(
        self,
        earthdata
    ):

        self.earthdata = earthdata

    async def search(
        self,
        sensor,
        lat,
        lng,
        start_date,
        end_date
    ):

        raise NotImplementedError

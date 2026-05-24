# Parcel extraction foundation

class ParcelExtractor:

    def __init__(
        self
    ):

        pass

    async def subset(
        self,
        granule,
        geometry
    ):

        raise NotImplementedError

    async def statistics(
        self,
        pixels
    ):

        raise NotImplementedError

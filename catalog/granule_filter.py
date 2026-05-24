# Granule filter foundation

class GranuleFilter:

    def __init__(self):

        pass

    async def quality(
        self,
        granules
    ):

        raise NotImplementedError

    async def freshness(
        self,
        granules
    ):

        raise NotImplementedError

    async def coverage(
        self,
        granules,
        geometry
    ):

        raise NotImplementedError

    async def select(
        self,
        granules
    ):

        raise NotImplementedError

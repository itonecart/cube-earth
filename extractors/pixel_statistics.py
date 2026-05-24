# Pixel statistics foundation

class PixelStatistics:

    def __init__(
        self
    ):

        pass

    async def mean(
        self,
        pixels
    ):

        raise NotImplementedError

    async def median(
        self,
        pixels
    ):

        raise NotImplementedError

    async def percentile(
        self,
        pixels,
        value
    ):

        raise NotImplementedError

    async def variability(
        self,
        pixels
    ):

        raise NotImplementedError

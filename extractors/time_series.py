# Time series foundation

class TimeSeries:

    def __init__(
        self
    ):

        pass

    async def trend(
        self,
        observations
    ):

        raise NotImplementedError

    async def persistence(
        self,
        observations
    ):

        raise NotImplementedError

    async def anomaly(
        self,
        observations,
        baseline
    ):

        raise NotImplementedError

    async def seasonality(
        self,
        observations
    ):

        raise NotImplementedError

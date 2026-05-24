# Limitations engine foundation

class LimitationsEngine:

    def __init__(
        self
    ):

        pass

    def sensor(
        self,
        sensor
    ):

        raise NotImplementedError

    def parcel(
        self,
        area
    ):

        raise NotImplementedError

    def temporal(
        self,
        observations
    ):

        raise NotImplementedError

    def disagreement(
        self,
        sources
    ):

        raise NotImplementedError

    def build(
        self,
        inputs
    ):

        raise NotImplementedError

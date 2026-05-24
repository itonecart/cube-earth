# Confidence engine foundation

class ConfidenceEngine:

    def __init__(
        self
    ):

        pass

    def sensor_quality(
        self,
        inputs
    ):

        raise NotImplementedError

    def temporal_quality(
        self,
        observations
    ):

        raise NotImplementedError

    def parcel_quality(
        self,
        parcel
    ):

        raise NotImplementedError

    def disagreement(
        self,
        sources
    ):

        raise NotImplementedError

    def build(
        self,
        quality,
        limitations
    ):

        raise NotImplementedError

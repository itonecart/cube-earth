# Quality engine foundation

class QualityEngine:

    def __init__(self):

        pass

    def cloud_quality(
        self,
        observations
    ):

        raise NotImplementedError

    def freshness(
        self,
        observations
    ):

        raise NotImplementedError

    def mixed_pixel(
        self,
        parcel_area,
        sensor_resolution
    ):

        raise NotImplementedError

    def disagreement(
        self,
        source_a,
        source_b
    ):

        raise NotImplementedError

    def confidence(
        self,
        quality_inputs
    ):

        raise NotImplementedError

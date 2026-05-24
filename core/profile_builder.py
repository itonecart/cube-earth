# Profile builder foundation

class ProfileBuilder:

    def __init__(self):

        pass

    def parcel_identity(
        self,
        parcel
    ):

        raise NotImplementedError

    def observations(
        self,
        sensor_results
    ):

        raise NotImplementedError

    def regional_context(
        self,
        context
    ):

        raise NotImplementedError

    def limitations(
        self,
        quality
    ):

        raise NotImplementedError

    def confidence(
        self,
        quality
    ):

        raise NotImplementedError

    def build(
        self,
        inputs
    ):

        raise NotImplementedError

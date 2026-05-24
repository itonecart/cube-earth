# Field request foundation

class FieldRequest:

    def __init__(
        self,
        lat,
        lng,
        year
    ):

        self.lat = lat

        self.lng = lng

        self.year = year

    def validate(
        self
    ):

        raise NotImplementedError

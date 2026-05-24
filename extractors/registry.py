# Extractor registry foundation

class ExtractorRegistry:

    def __init__(self):

        self.extractors = {}

    def register(
        self,
        name,
        extractor
    ):

        self.extractors[name] = extractor

    def get(
        self,
        name
    ):

        return self.extractors.get(
            name
        )

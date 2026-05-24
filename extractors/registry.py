# Extractor registry

from extractors.smap_extractor import SMAPExtractor


class ExtractorRegistry:

    def __init__(

        self,

        earthdata,

        settings

    ):

        self.extractors = {}

        self.register(

            "smap",

            SMAPExtractor(

                earthdata,

                settings

            )

        )

    def register(

        self,

        name,

        extractor

    ):

        self.extractors[
            name
        ] = extractor

    def get(

        self,

        name

    ):

        return self.extractors.get(

            name

        )

    def available(

        self

    ):

        return list(

            self.extractors.keys()

        )

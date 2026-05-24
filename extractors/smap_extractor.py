from extractors.base_extractor import BaseExtractor


class SMAPExtractor(

    BaseExtractor

):

    def __init__(

        self,

        earthdata,

        settings

    ):

        super().__init__(

            "smap"

        )

        self.earthdata = earthdata

        self.settings = settings

        self.collection = (

            "C2208420167-POCLOUD"

        )

    async def search(

        self,

        lat,

        lng,

        start_date,

        end_date

    ):

        bbox = (

            f"{lng-0.05},"

            f"{lat-0.05},"

            f"{lng+0.05},"

            f"{lat+0.05}"

        )

        return await (

            self.earthdata

            .granules(

                self.collection,

                bbox,

                start_date,

                end_date

            )

        )

    async def extract(

        self,

        granule,

        geometry

    ):

        return {

            "granule":

            granule,

            "geometry":

            geometry

        }

    async def quality(

        self,

        result

    ):

        return {

            "scale":

            "regional",

            "confidence":

            "high",

            "limitations":[

                (

                 "Not parcel "

                 "precise"

                )

            ]

        }

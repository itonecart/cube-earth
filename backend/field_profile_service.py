# Field profile service


class FieldProfileService:

    def __init__(

        self,

        cache,

        worker,

        profile,

        quality,

        confidence,

        limitations

    ):

        self.cache = cache

        self.worker = worker

        self.profile = profile

        self.quality = quality

        self.confidence = confidence

        self.limitations = limitations

    async def build_profile(

        self,

        lat,

        lng,

        year

    ):

        cache_key = (

            f"{lat}_"

            f"{lng}_"

            f"{year}"

        )

        cached = await (

            self.cache.get(

                cache_key

            )

        )

        if cached:

            return cached

        result = await (

            self.worker.run(

                {

                    "sensor":"smap",

                    "lat":lat,

                    "lng":lng,

                    "start_date":

                    (

                     f"{year}"

                     "-01-01"

                    ),

                    "end_date":

                    (

                     f"{year}"

                     "-12-31"

                    )

                }

            )

        )

        output = {

            "parcel_identity":{

                "lat":lat,

                "lng":lng

            },

            "regional_context":

            result,

            "quality":{},

            "confidence":{},

            "limitations":[]

        }

        await (

            self.cache.set(

                cache_key,

                output,

                86400

            )

        )

        return output

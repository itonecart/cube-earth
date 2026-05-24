# Extraction worker

class ExtractionWorker:

    def __init__(

        self,

        registry,

        cache

    ):

        self.registry = registry

        self.cache = cache

    async def run(

        self,

        job

    ):

        sensor = job.get(

            "sensor"

        )

        extractor = (

            self.registry.get(

                sensor

            )

        )

        if not extractor:

            return {

                "success": False,

                "reason":
                "extractor_not_found"

            }

        result = await (

            extractor.search(

                job["lat"],

                job["lng"],

                job["start_date"],

                job["end_date"]

            )

        )

        quality = await (

            extractor.quality(

                result

            )

        )

        return {

            "success": True,

            "sensor": sensor,

            "result": result,

            "quality": quality

        }

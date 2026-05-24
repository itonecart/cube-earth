# Extraction worker foundation

class ExtractionWorker:

    def __init__(
        self,
        extractors,
        cache
    ):

        self.extractors = extractors

        self.cache = cache

    async def run(
        self,
        job
    ):

        raise NotImplementedError

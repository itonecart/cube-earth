from catalog.auth import EarthdataAuth

from catalog.earthdata_client import (
    EarthdataClient
)

from config.settings import Settings

from cache.cache_manager import (
    CacheManager
)

from extractors.registry import (
    ExtractorRegistry
)

from workers.extraction_worker import (
    ExtractionWorker
)

from core.profile_builder import (
    ProfileBuilder
)

from core.quality_engine import (
    QualityEngine
)

from core.confidence_engine import (
    ConfidenceEngine
)

from core.limitations_engine import (
    LimitationsEngine
)

from backend.field_profile_service import (
    FieldProfileService
)


class Bootstrap:

    def build(

        self

    ):

        settings = Settings()

        auth = EarthdataAuth()

        earthdata = EarthdataClient(

            auth

        )

        cache = CacheManager()

        registry = ExtractorRegistry(

            earthdata,

            settings

        )

        worker = ExtractionWorker(

            registry,

            cache

        )

        profile = ProfileBuilder()

        quality = QualityEngine()

        confidence = (

            ConfidenceEngine()

        )

        limitations = (

            LimitationsEngine()

        )

        field_service = (

            FieldProfileService(

                cache,

                worker,

                profile,

                quality,

                confidence,

                limitations

            )

        )

        return field_service

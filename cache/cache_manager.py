# Cache foundation

class CacheManager:

    def __init__(self):

        pass

    async def get(
        self,
        key
    ):

        raise NotImplementedError

    async def set(
        self,
        key,
        value,
        ttl
    ):

        raise NotImplementedError

    async def delete(
        self,
        key
    ):

        raise NotImplementedError

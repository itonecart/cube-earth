import time


class CacheManager:

    def __init__(

        self

    ):

        self.store = {}

    async def get(

        self,

        key

    ):

        item = self.store.get(

            key

        )

        if not item:

            return None

        expires = item[

            "expires"

        ]

        if time.time() > expires:

            del self.store[

                key

            ]

            return None

        return item[

            "value"

        ]

    async def set(

        self,

        key,

        value,

        ttl

    ):

        self.store[

            key

        ] = {

            "value": value,

            "expires":

            time.time()

            + ttl

        }

    async def delete(

        self,

        key

    ):

        if key in self.store:

            del self.store[

                key
            ]

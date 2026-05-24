from backend.bootstrap import (
    Bootstrap
)

import asyncio


async def run_test():

    system = Bootstrap().build()

    result = await (

        system.build_profile(

            52.10,

            -9.70,

            2026

        )

    )

    print(result)


if __name__ == "__main__":

    loop = (

        asyncio.get_event_loop()

    )

    loop.run_until_complete(

        run_test()

    )

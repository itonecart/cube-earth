import asyncio

from backend.bootstrap import (
    Bootstrap
)


async def run():

    system = (

        Bootstrap()

        .build()

    )

    result = await (

        system.build_profile(

            52.10,

            -9.70,

            2026

        )

    )

    print(

        result

    )


if __name__ == "__main__":

    asyncio.run(

        run()

    )

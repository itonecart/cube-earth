import asyncio


async def run_test(

    service

):

    result = await (

        service.build_profile(

            52.10,

            -9.70,

            2026

        )

    )

    print(

        result

    )


def test():

    print(

        "Cube Earth integration foundation"

    )

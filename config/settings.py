# Settings foundation

import json


class Settings:

    def __init__(self):

        with open(
            "config/sensor_catalog.json"
        ) as f:

            self.catalog = json.load(f)

    def sensor(
        self,
        name
    ):

        return self.catalog.get(
            name
        )

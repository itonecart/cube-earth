# Request routing foundation

class RequestRouter:

    def __init__(
        self,
        field_service
    ):

        self.field_service = field_service

    async def route(
        self,
        request
    ):

        raise NotImplementedError

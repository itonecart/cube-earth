# Earthdata authentication foundation

class EarthdataAuth:

    def __init__(
        self,
        username=None,
        password=None
    ):

        self.username = username

        self.password = password

    async def login(
        self
    ):

        raise NotImplementedError

    async def token(
        self
    ):

        raise NotImplementedError

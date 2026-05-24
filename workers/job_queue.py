# Job queue foundation

class JobQueue:

    def __init__(self):

        pass

    async def enqueue(
        self,
        job
    ):

        raise NotImplementedError

    async def dequeue(
        self
    ):

        raise NotImplementedError

    async def status(
        self,
        job_id
    ):

        raise NotImplementedError

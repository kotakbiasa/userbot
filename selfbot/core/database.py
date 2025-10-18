import abc

from asyncpg import create_pool


class Database(abc.ABC):
    def __init__(self, **kwargs: any) -> None:
        self.db = None
        super().__init__(**kwargs)

    async def database(self) -> None:
        self.db = await create_pool(self.config["database_url"])

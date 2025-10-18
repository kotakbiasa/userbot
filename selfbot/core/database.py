import abc

import asyncpg

from .storage import PostgreStorage


class Database(abc.ABC):
    def __init__(self, **kwargs: any) -> None:
        self.db = None
        super().__init__(**kwargs)

    async def database(self) -> None:
        self.db = await asyncpg.create_pool(self.config["database_url"])
        await PostgreStorage.create_schema(self.db)

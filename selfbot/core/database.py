import abc

import asyncpg


class Database(abc.ABC):
    def __init__(self, **kwargs: any) -> None:
        self.db: asyncpg.Pool = None

        super().__init__(**kwargs)

    async def database(self) -> None:
        self.db = await asyncpg.create_pool(self.config["database_url"])

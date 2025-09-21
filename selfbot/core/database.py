import abc

import asyncpg


class Database(abc.ABC):
    def __init__(self, **kwargs: any) -> None:
        super().__init__(**kwargs)

    async def database(self) -> None:
        return await asyncpg.create_pool(self.config["database_url"])

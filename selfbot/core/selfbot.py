import asyncio
import logging

from httpx import AsyncClient

from .database import Database
from .dispatcher import Dispatcher
from .extender import Extender
from .telegram import Telegram


class Selfbot(Database, Dispatcher, Extender, Telegram):
    def __init__(self, config: dict) -> None:
        self.logger = logging.getLogger("Selfbot")
        self.config = config
        super().__init__()

    @classmethod
    async def launch(cls, config: dict) -> "Selfbot":
        selfbot = cls(config)
        try:
            selfbot.http = AsyncClient()
            await selfbot.run()
        finally:
            loop = asyncio.get_running_loop()
            if loop and not loop.is_closed():
                loop.call_soon(loop.stop)

        return selfbot

    async def stop(self) -> None:
        self.logger.info("Stopping Client...")
        await asyncio.gather(
            *[self.app.stop(), self.bot.stop(), self.http.aclose()],
            return_exceptions=True,
        )

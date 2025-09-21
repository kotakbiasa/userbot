import asyncio
import logging

from httpx import AsyncClient

from selfbot import __version__

from .database import Database
from .dispatcher import Dispatcher
from .extender import Extender
from .telegram import Telegram


class Selfbot(Database, Dispatcher, Extender, Telegram):
    def __init__(self, config: dict) -> None:
        self.logger = logging.getLogger("Selfbot")
        self.config = config

        self.loop = None
        self.http = None

        self.version = __version__

        super().__init__()

    @classmethod
    async def launch(
        cls, config: dict, *, loop: asyncio.AbstractEventLoop = None
    ) -> "Selfbot":
        if loop:
            asyncio.set_event_loop(loop)

        selfbot = cls(config)
        selfbot.loop, selfbot.http = loop, AsyncClient()
        try:
            await selfbot.run()
        finally:
            if loop and not loop.is_closed():
                loop.call_soon(loop.stop)

        return selfbot

    async def stop(self) -> None:
        self.logger.info("Stopping Client...")
        await asyncio.gather(
            *[self.app.stop(), self.bot.stop(), self.http.aclose()],
            return_exceptions=True,
        )

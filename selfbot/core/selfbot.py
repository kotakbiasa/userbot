import asyncio
import logging

from httpx import AsyncClient

from .database import Database
from .dispatcher import Dispatcher
from .extender import Extender
from .telegram import Telegram


class Selfbot(Database, Dispatcher, Extender, Telegram):
    def __init__(self, config: dict) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        super().__init__()

    @classmethod
    async def launch(cls, config: dict, loop: asyncio.AbstractEventLoop) -> "Selfbot":
        selfbot = cls(config)
        try:
            selfbot.http = AsyncClient(http2=True)
            selfbot.loop = loop
            await selfbot.run()
        finally:
            await selfbot.stop()

        return selfbot

    async def stop(self) -> None:
        try:
            await asyncio.gather(
                *(
                    self.dispatch("closing"),
                    self.app.stop(),
                    self.bot.stop(),
                    self.http.aclose(),
                ),
                return_exceptions=True,
            )
            await self.db.close()
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
        else:
            self.logger.info(f"{self.__class__.__name__} Stopped")

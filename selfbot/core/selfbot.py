import asyncio
import logging
import pathlib

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
    async def launch(cls, config: dict) -> "Selfbot":
        selfbot = cls(config)
        try:
            selfbot.http = AsyncClient(timeout=900)
            await selfbot.run()
        finally:
            loop = asyncio.get_running_loop()
            if loop and not loop.is_closed():
                loop.call_soon(loop.stop)

        return selfbot

    async def stop(self) -> None:
        self.logger.info(f"Stopping {self.__class__.__name__}...")
        try:
            await asyncio.gather(
                *[
                    self.dispatch("stopping"),
                    self.app.stop(),
                    self.bot.stop(),
                    self.http.aclose(),
                ],
                return_exceptions=True,
            )
            try:
                await self.db.close()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")

    @property
    def _git(self) -> str:
        cwd = pathlib.Path.cwd().resolve()
        while cwd != cwd.parent:
            if (cwd / ".git").is_dir():
                return str(cwd)

            cwd = cwd.parent

        return str(pathlib.Path.cwd())

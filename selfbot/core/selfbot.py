import asyncio
import logging
import pathlib
import os

from httpx import AsyncClient
from pyrogram import Client

try:
    from pytgcalls import PyTgCalls
except ImportError:
    PyTgCalls = None

from .database import Database
from .dispatcher import Dispatcher
from .extender import Extender
from .telegram import Telegram


class Selfbot(Database, Dispatcher, Extender, Telegram):
    def __init__(self, config: dict) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        # --- Inisialisasi Klien Asisten ---
        self.assistant_client = None
        self.assistant = None
        assistant_session = self.config.get("assistant_session")

        if PyTgCalls and assistant_session:
            self.logger.info("Assistant session found, initializing assistant client...")
            self.assistant_client = Client(
                name="assistant",
                session_string=assistant_session,
                api_id=self.config.get("api_id"),
                api_hash=self.config.get("api_hash"),
                in_memory=True
            )
            self.assistant = PyTgCalls(self.assistant_client)
        elif not assistant_session:
            self.logger.warning("ASSISTANT_SESSION not set. VCall module will be disabled.")
        else:
            self.logger.error("py-tgcalls is not installed. VCall module will be disabled.")
        # --- Akhir Inisialisasi ---

        super().__init__()

    @classmethod
    async def launch(cls, config: dict) -> "Selfbot":
        selfbot = cls(config)
        try:
            selfbot.http = AsyncClient(timeout=900)
            if selfbot.assistant_client:
                await selfbot.assistant_client.start()
            if selfbot.assistant:
                await selfbot.assistant.start()
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
                    self.assistant.stop() if self.assistant else asyncio.sleep(0),
                    self.assistant_client.stop()
                    if self.assistant_client
                    else asyncio.sleep(0),
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

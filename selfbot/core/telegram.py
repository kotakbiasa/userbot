import abc
import asyncio
import contextlib
import functools
import os
import pathlib
import signal

from pyrogram import Client
from pyrogram import filters as flt
from pyrogram.enums import ParseMode
from pyrogram.handlers import (
    CallbackQueryHandler,
    ChosenInlineResultHandler,
    InlineQueryHandler,
    MessageHandler,
)
from pyrogram.raw.types import (
    UpdateBotInlineQuery,
    UpdateBotInlineSend,
    UpdateInlineBotCallbackQuery,
    UpdateNewChannelMessage,
    UpdateNewMessage,
)
from pyrogram.storage import FileStorage
from pyrogram.types import LinkPreviewOptions, Update

commons = {
    "workdir": "./selfbot/storage/",
    "parse_mode": ParseMode.HTML,
    "sleep_threshold": 900,
    "max_message_cache_size": 0,
    "link_preview_options": LinkPreviewOptions(is_disabled=True),
    "no_joined_notifications": True,
}


class Telegram(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.app = self._app
        self.bot = self._bot

        self.__idle__ = None
        self.handlers = {}

        super().__init__(**kwargs)

    async def run(self) -> None:
        if self.__idle__ and not self.__idle__.is_set():
            raise RuntimeError("Selfbot Running")

        self.logger.info(
            f"{'Restart' if os.path.exists('r.txt') else 'Start'}ing Client..."
        )
        try:
            await self.start()
        except Exception as e:
            self.logger.error(str(e))
        else:
            self.logger.info("Client Started")
            await self.idle()
        finally:
            await self.stop()
            self.logger.info("Client Stopped")

    async def start(self) -> None:
        async def migrate(name: str, key: str) -> None:
            if self.config.get(key):
                async with Client(name, session_string=self.config[key]) as client:
                    await self._migrate(client)

        await asyncio.gather(
            migrate(self.app.name, "app_session_string"),
            migrate(self.bot.name, "bot_session_string"),
        )
        _, __, self.db = await asyncio.gather(
            self.app.start(), self.bot.start(), self.database()
        )
        await self.app.resolve_peer(self.bot.me.username)
        await asyncio.gather(
            asyncio.to_thread(self.loads), asyncio.to_thread(self.safe)
        )
        self.loop.create_task(self.dispatch("starting"))

    async def idle(self) -> None:
        if self.__idle__ and not self.__idle__.is_set():
            raise RuntimeError("Selfbot Idling")

        signames = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)

        def sighandler(signum: int) -> None:
            if self.__idle__:
                self.__idle__.set()

        for signame in signames:
            self.loop.add_signal_handler(
                signame, functools.partial(sighandler, signame)
            )

        self.__idle__ = asyncio.Event()
        try:
            await self.__idle__.wait()
        finally:
            for signame in signames:
                with contextlib.suppress(Exception):
                    self.loop.remove_signal_handler(signame)

    def updates(self) -> None:
        fltapp = flt.user(self.app.me.id)
        events = {
            "message_in": (
                self.app,
                MessageHandler,
                flt.incoming & (~flt.me & ~flt.bot & ~flt.via_bot),
                -1,
            ),
            "message_out": (
                self.app,
                MessageHandler,
                (flt.me & (flt.text | flt.caption)) & ~flt.via_bot,
                -1,
            ),
            "inline_query": (self.bot, InlineQueryHandler, fltapp, -1),
            "inline_result": (self.bot, ChosenInlineResultHandler, fltapp, -1),
            "inline_callback": (self.bot, CallbackQueryHandler, flt.all, -1),
        }
        for name, (client, handler, filters, group) in events.items():
            if name in self.handlers:
                client.remove_handler(*self.handlers.pop(name))

            if name in self.listeners and self.listeners[name]:

                async def callback(_: Client, event: Update, bound=name) -> None:
                    await self.dispatch(bound, event)

                dispatcher = (handler(callback, filters), group)
                try:
                    client.add_handler(*dispatcher)
                finally:
                    self.handlers[name] = dispatcher

    def safe(self) -> None:
        self.config.clear()
        for key in list(os.environ):
            if key.endswith("_SESSION_STRING"):
                os.environ.pop(key)
            elif key in ["BRANCH", "DATABASE_URL", "STICKER_FILE_ID"]:
                self.config[key.lower()] = os.environ[key]

    @property
    def _app(self) -> Client:
        return self._build("app", updates=(UpdateNewChannelMessage, UpdateNewMessage))

    @property
    def _bot(self) -> Client:
        return self._build(
            "bot",
            updates=(
                UpdateBotInlineQuery,
                UpdateBotInlineSend,
                UpdateInlineBotCallbackQuery,
            ),
        )

    @staticmethod
    async def _migrate(client: Client) -> None:
        attrs = [
            "dc_id",
            "api_id",
            "test_mode",
            "auth_key",
            "date",
            "user_id",
            "is_bot",
        ]
        creds = await asyncio.gather(
            *[getattr(client.storage, attr)() for attr in attrs]
        )
        files = FileStorage(client.name, pathlib.Path(commons["workdir"]))
        await files.open()
        await asyncio.gather(
            *[getattr(files, attr)(cred) for attr, cred in zip(attrs, creds)]
        )

    @staticmethod
    def _build(name: str, updates: tuple = ()) -> Client:
        client = Client(name, **commons)
        if updates:
            client.dispatcher.update_parsers = {
                k: v
                for k, v in client.dispatcher.update_parsers.items()
                if k in updates
            }

        setattr(client, "workers", len(client.dispatcher.update_parsers))
        return client

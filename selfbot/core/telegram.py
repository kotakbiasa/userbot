import abc
import asyncio
import contextlib
import functools
import os
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
from pyrogram.handlers.handler import Handler
from pyrogram.raw.types import (
    UpdateBotInlineQuery,
    UpdateBotInlineSend,
    UpdateInlineBotCallbackQuery,
    UpdateNewChannelMessage,
    UpdateNewMessage,
)
from pyrogram.types import LinkPreviewOptions, Update

from .storage import PostgresStorage


class Telegram(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.app: Client = None
        self.bot: Client = None

        self.__event__: asyncio.Event = None
        self.handlers: dict[str, Handler] = {}

        super().__init__(**kwargs)

    async def run(self) -> None:
        if self.__event__ and not self.__event__.is_set():
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
        await self.database()

        self.app = self._app
        self.bot = self._bot

        self.logger.info("Starting App...")
        await self.app.start()
        self.logger.info("Starting Bot...")
        await self.bot.start()
        await asyncio.gather(
            self.app.resolve_peer(self.bot.me.username),
            asyncio.to_thread(self.loads),
            asyncio.to_thread(self.conf),
        )
        asyncio.create_task(self.dispatch("starting"))

    async def idle(self) -> None:
        if self.__event__ and not self.__event__.is_set():
            raise RuntimeError("Selfbot Idling")

        signames = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)

        def sighandler(signum: int) -> None:
            if self.__event__:
                self.__event__.set()

        for signame in signames:
            asyncio.get_running_loop().add_signal_handler(
                signame, functools.partial(sighandler, signame)
            )

        self.__event__ = asyncio.Event()
        try:
            await self.__event__.wait()
        finally:
            for signame in signames:
                with contextlib.suppress(Exception):
                    asyncio.get_running_loop().remove_signal_handler(signame)

    def updates(self) -> None:
        fltapp = flt.user(self.app.me.id)
        events = {
            "message_in": (
                self.app,
                MessageHandler,
                (flt.mentioned | (flt.incoming & flt.private))
                & (~flt.me & ~flt.bot & ~flt.via_bot),
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
                    asyncio.create_task(self.dispatch(bound, event))

                dispatcher = (handler(callback, filters), group)
                try:
                    client.add_handler(*dispatcher)
                finally:
                    self.handlers[name] = dispatcher

    def conf(self) -> None:
        self.config.clear()
        for key in list(os.environ):
            if key in ["DATABASE_URL", "GEMINI_API_KEY", "STICKER_FILE_ID"]:
                self.config[key.lower()] = os.environ[key]

    def build(self, name: str, updates: tuple = ()) -> Client:
        client = Client(
            name=name,
            api_id=self.config.get("api_id"),
            api_hash=self.config.get("api_hash"),
            parse_mode=ParseMode.HTML,
            sleep_threshold=15,
            max_message_cache_size=0,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            no_joined_notifications=True,
            storage_engine=PostgresStorage(name, self.db),
        )
        if updates:
            client.dispatcher.update_parsers = {
                k: v
                for k, v in client.dispatcher.update_parsers.items()
                if k in updates
            }

        setattr(client, "workers", len(client.dispatcher.update_parsers))
        return client

    @property
    def _app(self) -> Client:
        return self.build("app", updates=(UpdateNewChannelMessage, UpdateNewMessage))

    @property
    def _bot(self) -> Client:
        return self.build(
            "bot",
            updates=(
                UpdateBotInlineQuery,
                UpdateBotInlineSend,
                UpdateInlineBotCallbackQuery,
            ),
        )

import abc
import asyncio
import contextlib
import datetime
import functools
import os
import signal

from pyrogram import Client
from pyrogram import filters as flt
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.errors import PeerIdInvalid, UserIsBlocked
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
from pyrogram.types import LinkPreviewOptions, Update

from selfbot import __version__
from selfbot.core.storage import PostgreStorage
from selfbot.utils import fmtsec, fmtstr, ikm


class Telegram(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.app = None
        self.bot = None
        self.__idle__ = None
        self.handlers = {}
        super().__init__(**kwargs)

    async def run(self) -> None:
        if self.__idle__ and not self.__idle__.is_set():
            raise RuntimeError("Selfbot Running")

        tmp = os.path.exists("/tmp/r.json")
        self.logger.info(f"{'Res' if tmp else 'S'}tarting Client...")
        now = datetime.datetime.now(datetime.UTC)
        try:
            await self.start()
        except Exception as e:
            self.logger.error(str(e))
        else:
            self.logger.info("Client Started")
            await self.bot.send_message(
                self.app.me.id,
                fmtstr(
                    f"Selfbot {'Res' if tmp else 'S'}tarted",
                    {
                        "Version": f"{__version__}\n",
                        "Handlers": len(self.handlers),
                        "Listeners": len(self.listeners),
                        "Modules": len(self.modules),
                    },
                    fmtsec(now),
                ),
                disable_notification=True,
                reply_markup=ikm(
                    [
                        [
                            (
                                "Commit History",
                                "url",
                                f"{self.config.get(
                'remote', 'https://github.com/DeltaUniverse/selfbot'
            ).removesuffix('.git')}/commits/{self.config.get('branch', 'staging')}",
                            )
                        ],
                        [
                            ("Ping", "switch_inline_query_current_chat", "ping"),
                            ("Help", "switch_inline_query_current_chat", "help"),
                        ],
                    ]
                ),
            )
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
        try:
            await self.bot.send_chat_action(self.app.me.id, ChatAction.TYPING)
        except PeerIdInvalid:
            msg = await self.app.send_message(self.bot.me.id, "/start")
            await msg.delete()
        except UserIsBlocked:
            await self.app.unblock_user(self.bot.me.id)

        self.logger.info("Dispatch On Start...")
        await self.dispatch("starting")
        await self.dispatch("started")
        self.logger.info("On Start Dispatched")

    async def idle(self) -> None:
        if self.__idle__ and not self.__idle__.is_set():
            raise RuntimeError("Selfbot Idling")

        signames = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)

        def sighandler(signum: int) -> None:
            if self.__idle__:
                self.__idle__.set()

        for signame in signames:
            asyncio.get_running_loop().add_signal_handler(
                signame, functools.partial(sighandler, signame)
            )

        self.__idle__ = asyncio.Event()
        try:
            await self.__idle__.wait()
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
                & (~flt.me & ~flt.bot & ~flt.via_bot & ~flt.service),
                -1,
            ),
            "message_out": (
                self.app,
                MessageHandler,
                (flt.me & (flt.text | flt.caption)) & ~flt.via_bot,
                -1,
            ),
            "message_bot": (self.bot, MessageHandler, fltapp, -1),
            "inline_query": (self.bot, InlineQueryHandler, fltapp, -1),
            "inline_result": (self.bot, ChosenInlineResultHandler, fltapp, -1),
            "inline_callback": (self.bot, CallbackQueryHandler, fltapp, -1),
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
            storage_engine=PostgreStorage(name, self.db),
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
                UpdateNewMessage,
            ),
        )

import asyncio
import datetime
import os
import re
import sys

from pyrogram import filters
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm, shell

pattern = re.compile(r"^r$")


class System(Module):
    name = "System"
    cmds = "r"
    desc = "Restart Selfbot"

    async def on_starting(self) -> None:
        data = await asyncio.to_thread(self._get, "r.txt")
        if data:
            await self.client.bot.edit_inline_text(
                data[0],
                fmtstr(
                    "Selfbot Restarted",
                    {
                        "Version": self.client.version,
                        "Modules": len(self.client.modules),
                        "Handlers": len(self.client.handlers),
                        "Listeners": len(self.client.listeners),
                    },
                    fmtsec(datetime.datetime.fromtimestamp(float(data[1]))),
                ),
                reply_markup=ikm(("Close", b"0")),
            )

        self.remote = self.client.config.get(
            "remote", "https://github.com/DeltaUniverse/selfbot"
        )
        self.branch = self.client.config.get("branch", "staging")

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        res = await event._client.get_inline_bot_results(self.client.bot.me.id, "r")
        await asyncio.gather(
            event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
                reply_parameters=ReplyParameters(
                    message_id=event.reply_to_message_id or event.id
                ),
            ),
            event.delete(True),
        )

    @listener.handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent(
                        "<code>Update and Restart...</code>"
                    ),
                )
            ],
            cache_time=900,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        if getattr(self.client, "restart", None):
            return await event.edit_message_text(
                "<code>Restart is Called</code>", reply_markup=ikm(("Close", b"0"))
            )

        setattr(self.client, "restart", True)

        if os.path.isdir(".git"):
            await shell("rm -fr .git")

        await asyncio.gather(
            event.edit_message_text("<code>Fetch Upstream...</code>"),
            shell(
                f"git init; git remote add origin {self.remote}; git fetch"
                f"; git reset --hard origin/{self.branch}"
            ),
        )
        await asyncio.gather(
            event.edit_message_text("<code>Update Dependencies...</code>"),
            shell("pip install -U pip; pip install -r requirements.txt"),
        )
        await asyncio.gather(
            event.edit_message_text("<code>Restart System...</code>"),
            asyncio.to_thread(
                self._put,
                "r.txt",
                f"{event.inline_message_id}\n{datetime.datetime.now().timestamp()}",
            ),
        )

        try:
            self.client.__event__.set()
        finally:
            os.execv(sys.executable, (sys.executable, "-m", "selfbot"))

    @staticmethod
    def _get(file: str) -> tuple | None:
        if os.path.exists(file):
            with open(file) as f:
                try:
                    data = f.readlines()
                    return data[0], float(data[1])
                finally:
                    os.remove(file)

        return None

    @staticmethod
    def _put(file: str, text: str) -> None:
        with open(file, "w") as f:
            f.write(text)

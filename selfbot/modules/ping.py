import asyncio
import datetime
import re

from pyrogram import Client, filters
from pyrogram.raw import functions
from pyrogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    Update,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm

pattern = re.compile(r"^p(?:ing)?$")


class Ping(Module):
    name = "Ping"

    cmds = "p(ing)?"
    desc = {"?": "Optional", "e.g.": "ping"}

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event)

    @listener.handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent("<code>...</code>"),
                )
            ],
            cache_time=0,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        await self.respond(event)

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        if event.from_user.id != self.client.app.me.id:
            return await event.answer("Who are You?", show_alert=True, cache_time=0)

        await self.respond(event)

    async def ping(self, client: Client) -> str:
        now = datetime.datetime.now()
        await client.invoke(functions.Ping(ping_id=0))
        return fmtsec(now, 1)

    async def respond(self, event: Update) -> None:
        edit: callable
        if isinstance(event, Message):
            edit = event.edit_text
        else:
            edit = event.edit_message_text

        if isinstance(event, Message):
            await edit("<code>...</code>")
        else:
            await event.edit_message_reply_markup(
                ikm(("...", "user_id", event._client.me.id))
            )

        now, (app, bot) = datetime.datetime.now(), await asyncio.gather(
            self.ping(self.client.app), self.ping(event._client)
        )
        await edit(
            fmtstr("Pong!", {"App": app, "Bot": bot}, fmtsec(now)),
            reply_markup=ikm([[("Ping!", b"ping")], [("Close", b"0")]]),
        )

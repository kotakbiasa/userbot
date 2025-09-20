import asyncio
import datetime
import re

from pyrogram import Client, filters
from pyrogram.raw.functions import Ping
from pyrogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
    Update,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm

pattern = re.compile(r"^ping$")


class Network(Module):
    name = "Network"
    cmds = "ping"
    desc = "Selfbot Latency"

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        res = await event._client.get_inline_bot_results(self.client.bot.me.id, "ping")
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
                    input_message_content=InputTextMessageContent("<code>...</code>"),
                )
            ],
            cache_time=900,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        await self.edit(event)

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        if event.from_user.id != self.client.app.me.id:
            return await event.answer("Who are You?", show_alert=True, cache_time=900)

        await event.answer(cache_time=0)
        await self.edit(event)

    async def edit(self, event: Update) -> None:
        await event.edit_message_text("<code>Pinging...</code>")
        now, (app, bot) = datetime.datetime.now(), await asyncio.gather(
            self.ping(self.client.app), self.ping(event._client)
        )
        await event.edit_message_text(
            fmtstr("Selfbot Latency", {"App": app, "Bot": bot}, fmtsec(now)),
            reply_markup=ikm([[("Ping!", b"ping")], [("Close", b"0")]]),
        )

    async def ping(self, client: Client) -> str:
        now = datetime.datetime.now()
        await client.invoke(Ping(ping_id=0))
        res = f"{(datetime.datetime.now() - now).total_seconds() * 1e3:.2f}".rstrip(
            "0"
        ).rstrip(".")
        return f"{res} ms"

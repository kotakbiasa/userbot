import asyncio
import datetime
import re

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
from selfbot.utils import fmtsec, fmtstr, ids, ikm

pattern = re.compile(
    r"^tr(?:\s-to\s(?P<lang>[a-zA-Z\-]{2,6}))?(?:\s(?P<text>.+))?$", re.DOTALL
)


class Translate(Module):
    name = "Translate"

    cmds = "(tr) {(-to) lang} {content}"
    desc = {"lang": "Language Code", "content": "String or Reply to Content"}

    async def on_startup(self) -> None:
        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

    @listener.handler(filters.regex(pattern), 1)
    async def on_message(self, event: Message) -> None:
        data = pattern.match(event.content).groupdict()
        args = {}

        if not data["text"]:
            if event.quote and event.quote.text:
                data["text"] = event.quote.text
                args = {
                    "quote": event.quote.text,
                    "quote_entities": event.quote.entities,
                    "quote_position": event.quote.position,
                }
            elif event.reply_to_message and event.reply_to_message.content:
                data["text"] = event.reply_to_message.content
            else:
                return await event.edit("<code>Reply to Content or Give a Text</code>")

        async with self.lock:
            await self.data.put(data)

        if event.external_reply and event.external_reply.message_id:
            args.update(
                {
                    "chat_id": event.external_reply.chat.id,
                    "message_id": event.external_reply.message_id,
                }
            )
        else:
            args.update(
                {"chat_id": event.chat.id, "message_id": event.reply_to_message_id}
            )

        res = await event._client.get_inline_bot_results(
            self.client.bot.me.id, event.content
        )
        await asyncio.gather(
            event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
                reply_parameters=ReplyParameters(**args),
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
                        "<code>Translating...</code>"
                    ),
                )
            ],
            cache_time=900,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_chosen_inline_result(self, event: ChosenInlineResult) -> None:
        if self.data.empty():
            return await self.client.app.delete_messages(
                *ids(event.inline_message_id), True
            )

        async with self.lock:
            data = await self.data.get()

        now = datetime.datetime.now()
        res = await self.client.app.translate_text(data["lang"] or "id", data["text"])

        await event.edit_message_text(
            fmtstr(
                "Translated Text",
                {"Language": data["lang"] or "id", "Result": res.text},
                fmtsec(now),
            ),
            reply_markup=ikm(("Close", b"0")),
        )

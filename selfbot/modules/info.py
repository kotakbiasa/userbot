import asyncio
import datetime
import json
import os
import re

from pyrogram import filters
from pyrogram.enums import ChatType, MessageEntityType
from pyrogram.errors import MediaCaptionTooLong, MessageTooLong, RPCError
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputMediaPhoto,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ids, ikm

pattern = re.compile(r"^info(?:\s(?P<chat>.+))?$")


class Info(Module):
    name = "Info"

    cmds = "info {chat}?"
    desc = {
        "chat": "<Reply to Chat or Quote Text> or Chat ID or Username or Mention (Default: Current Chat)"
    }

    async def on_starting(self) -> None:
        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        data, args = pattern.match(event.content).groupdict(), {}
        if not data["chat"]:
            if event.quote and event.quote.text:
                data["chat"] = event.quote.text
                args = {
                    "quote": event.quote.text,
                    "quote_entities": event.quote.entities,
                    "quote_position": event.quote.position,
                }
            elif event.reply_to_message:
                data["chat"] = (
                    event.reply_to_message.sender_chat.id
                    if event.reply_to_message.sender_chat
                    else event.reply_to_message.from_user.id
                )
            else:
                data["chat"] = event.chat.id
        else:
            if (
                event.entities
                and event.entities[0].type == MessageEntityType.TEXT_MENTION
            ):
                data["chat"] = event.entities[0].user.id

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
                        "<code>Get Chat...</code>"
                    ),
                )
            ],
            cache_time=0,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        if self.data.empty():
            return await self.client.app.delete_messages(
                *ids(event.inline_message_id), True
            )

        async with self.lock:
            data = await self.data.get()

        now = datetime.datetime.now()
        try:
            chat = await self.client.app.get_chat(data["chat"])
        except RPCError as e:
            await event.edit_message_text(
                f"<code>{e.__class__.__name__}</code>\n\n<b>{fmtsec(now)}</b>",
                reply_markup=ikm(("Close", b"0")),
            )
        else:
            text = {
                k.title()
                .replace("Id", "ID")
                .replace("Dc", "DC")
                .replace("_", " "): v.name if isinstance(v, ChatType) else v
                for k, v in chat.__dict__.items()
                if isinstance(v, int | str | ChatType) and not k.startswith("_")
            }
            if chat.photo:
                photo = await self.client.app.download_media(chat.photo.big_file_id)
                await event.edit_message_media(InputMediaPhoto(photo))
                if os.path.exists(photo):
                    await asyncio.to_thread(os.remove, photo)

            try:
                await event.edit_message_text(
                    fmtstr("Chat Information", text, fmtsec(now)),
                    reply_markup=ikm(("Close", b"0")),
                )
            except (MessageTooLong, MediaCaptionTooLong) as e:
                link = (
                    await self.client.http.post(
                        "https://paste.rs", data=json.dumps(text, indent=2).encode()
                    )
                ).text.strip()
                await event.edit_message_text(
                    fmtstr("Chat Information", e.__class__.__name__, fmtsec(now)),
                    reply_markup=ikm([("Full", "url", link), ("Close", b"0")]),
                )

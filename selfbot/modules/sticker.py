import asyncio
import re

from pyrogram import filters
from pyrogram.raw.functions.messages import GetMyStickers
from pyrogram.raw.functions.stickers import AddStickerToSet, CreateStickerSet
from pyrogram.raw.types import InputStickerSetItem, InputStickerSetShortName
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)
from pyrogram.utils import get_input_media_from_file_id

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ids, ikm

pattern = re.compile(
    r"^"
    r"(?P<mode>add|set|get)sticker"
    r"(?:\s(?P<name>[a-zA-Z][a-zA-Z0-9_]+))?"
    r"(?:\s-e\s(?P<emoji>.+))?"
    r"$"
)


class Sticker(Module):
    name = "Sticker"

    async def on_startup(self) -> None:
        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

        self.last = None
        self.sets = {}

        res = await self.client.app.invoke(GetMyStickers(offset_id=0, limit=0))
        if res and res.sets:
            for i in res.sets:
                self.sets[i.set.short_name] = i.set.count

    @listener.handler(filters.regex(pattern), 1)
    async def on_message(self, event: Message) -> None:
        data = pattern.match(event.content).groupdict()

        if data["mode"] not in ["del", "get"]:
            if not event.reply_to_message or (
                event.reply_to_message and not event.reply_to_message.sticker
            ):
                return await event.edit("<code>Reply to Sticker</code>")

            data["source"] = {
                "file": event.reply_to_message.sticker.file_id,
                "name": event.reply_to_message.sticker.set_name or "N/A",
            }

            if not data["emoji"]:
                data["emoji"] = event.reply_to_message.sticker.emoji or "🤖"

            if not data["name"]:
                if not self.last:
                    return await event.edit("<code>Sticker Short Name Required</code>")

                data["name"] = self.last

        async with self.lock:
            await self.data.put(data)

        res = await event._client.get_inline_bot_results(
            self.client.bot.me.id, event.content
        )
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
    async def on_chosen_inline_result(self, event: ChosenInlineResult) -> None:
        if self.data.empty():
            return await self.client.app.delete_messages(
                *ids(event.inline_message_id), True
            )

        async with self.lock:
            data = await self.data.get()

        sec = self.client.loop.time()

        if data["mode"] == "get":
            await event.edit_message_text(
                fmtstr(
                    "List Owned Stickers",
                    [f"{k} ({v})" for k, v in self.sets.items()],
                    fmtsec(sec),
                ),
                reply_markup=ikm(("Close", b"0")),
            )

        else:
            sticker = InputStickerSetItem(
                document=get_input_media_from_file_id(data["source"]["file"]).id,
                emoji=data["emoji"],
            )

            text = ""
            func = None

            if data["mode"] == "add":
                text = "Sticker Added to Set"
                func = AddStickerToSet(
                    stickerset=InputStickerSetShortName(short_name=data["name"]),
                    sticker=sticker,
                )
            else:
                text = "Sticker Set Created"
                func = CreateStickerSet(
                    user_id=await self.client.app.resolve_peer("me"),
                    title="Sticker Set",
                    short_name=data["name"],
                    stickers=[sticker],
                )

            try:
                last = await self.client.app.invoke(func)
            except Exception as e:
                return await event.edit_message_text(
                    f"<code>{e.__class__.__name__}</code>\n\n<b>{fmtsec(sec)}</b>",
                    reply_markup=ikm(("Close", b"0")),
                )
            else:
                args = {
                    "text": fmtstr(
                        text,
                        {
                            "Name": last.set.short_name,
                            "Emoji": data["emoji"],
                            "Source": data["source"]["name"],
                        },
                        fmtsec(sec),
                    ),
                    "reply_markup": ikm(
                        [
                            [
                                (
                                    "Old",
                                    "url",
                                    f"https://t.me/addstickers/{data['source']['name']}",
                                ),
                                (
                                    "New",
                                    "url",
                                    f"https://t.me/addstickers/{last.set.short_name}",
                                ),
                            ],
                            [("Close", b"0")],
                        ]
                    ),
                }

                try:
                    await event.edit_message_text(**args)
                finally:
                    async with self.lock:
                        self.last = last.set.short_name
                        self.sets[self.last] = last.set.count

import asyncio
import re

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import ikm

pattern = re.compile(r"^help(?:/(?P<mod>[a-z]+))$")


class Help(Module):
    name = "Help"
    hide = True

    async def on_startup(self) -> None:
        self.mod = {}

        ikb = []
        for mod in self.client.modules.values():
            if not mod.hide:
                self.mod[mod.name.lower()] = f"{mod.name}\n\n{mod.cmds}\n\n{mod.desc}"
                ikb.append((mod.name, f"help/{mod.name.lower()}"))

        self.ikb = [ikb[i : i + 2] for i in range(0, len(ikb), 2)]
        self.ikb.append([("Close", b"0")])

    @listener.handler(filters.regex(pattern), 1)
    async def on_message(self, event: Message) -> None:
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
                    input_message_content=InputTextMessageContent(f"<code>...</code>"),
                )
            ],
            cache_time=900,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_chosen_inline_result(self, event: ChosenInlineResult) -> None:
        await event.edit_message_text(
            "<b>Selfbot Modules</b>", reply_markup=ikm(self.ikb)
        )

    @listener.handler(filters.regex(pattern), 4)
    async def on_callback_query(self, event: CallbackQuery) -> None:
        data = pattern.match(event.data).groupdict()

        if not self.mod.get(data["mod"]):
            return await event.answer("None", show_alert=True, cache_time=900)

        await event.answer(self.mod[data["mod"]], show_alert=True, cache_time=900)

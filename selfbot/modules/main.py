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

pattern = re.compile(r"^help/?(mod|info|page)?/?(\d{1}|[a-z]+)?$")


class Main(Module):
    name = "Main"
    hide = True

    async def on_startup(self) -> None:
        self.mods = {}
        self.maps = {}
        self.ikbs = []

        mods = [mod for mod in self.client.modules.values() if not mod.hide]
        mods.sort(key=lambda mod: mod.name.lower())

        page = []

        for i, mod in enumerate(mods):
            name = mod.name.lower()

            self.maps[name] = len(self.ikbs)

            desc = "\n".join([f"    • <code>{i}</code>" for i in mod.desc])
            self.mods[name] = (
                f"<b>{mod.name}</b>\n\n  <b>Pattern</b>\n    <code>{mod.cmds}</code>"
                f"\n\n{desc}"
            )

            page.append((mod.name, f"help/mod/{name}"))
            if len(page) == 4:
                self.ikbs.append([page[i : i + 2] for i in range(0, 4, 2)])
                page = []

        if page:
            self.ikbs.append([page[i : i + 2] for i in range(0, len(page), 2)])

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
            "<b>Selfbot Modules</b>", reply_markup=ikm(self.build(0))
        )

    @listener.handler(filters.regex(pattern), 4)
    async def on_callback_query(self, event: CallbackQuery) -> None:
        act, val = pattern.match(event.data).groups()

        if act == "mod":
            page = self.maps.get(val, 0)
            await event.edit_message_text(
                self.mods[val],
                reply_markup=ikm([("« Back", f"help/page/{page}"), ("Close", b"0")]),
            )

        elif act == "page":
            await event.edit_message_text(
                "<b>Selfbot Modules</b>", reply_markup=ikm(self.build(int(val)))
            )

        elif act == "info":
            await event.answer(
                f"Page {int(val) + 1} of {len(self.ikbs)}",
                show_alert=True,
                cache_time=900,
            )

    def build(self, page: int = 0) -> list:
        ikbs = len(self.ikbs)
        page = max(0, min(page, ikbs - 1))

        ikb = self.ikbs[page][:]
        ikb.append([("Page Info", f"help/info/{page}")])

        nav = []
        if page > 0:
            nav.append((f"« ({page})", f"help/page/{page - 1}"))

        nav.append(("Close", b"0"))

        if page < ikbs - 1:
            nav.append((f"({page + 2}) »", f"help/page/{page + 1}"))

        ikb.append(nav)

        return ikb

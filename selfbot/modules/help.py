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


class Help(Module):
    name = "Help"
    hide = True

    async def on_starting(self) -> None:
        self.mod = {}
        self.map = {}
        self.ikb = []

        mods = [mod for mod in self.client.modules.values() if not mod.hide]
        page = []
        for i, mod in enumerate(mods):
            name = mod.name.lower()
            self.map[name] = len(self.ikb)
            self.mod[name] = (
                f"<b>{mod.name}</b>"
                f"\n\n{' ' * 2}<b>Pattern</b>\n{' ' * 4}<code>{mod.cmds}</code>"
                f"\n\n{self._fmthelp(mod.desc)}"
            )
            page.append((mod.name, f"help/mod/{name}"))
            if len(page) == 4:
                self.ikb.append([page[i : i + 2] for i in range(0, 4, 2)])
                page = []

        if page:
            self.ikb.append([page[i : i + 2] for i in range(0, len(page), 2)])

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
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
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        await event.edit_message_text(
            "<b>Selfbot Modules</b>", reply_markup=ikm(self.build())
        )

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        act, val = pattern.match(event.data).groups()
        if act == "info":
            return await event.answer(
                (
                    f"Selfbot Version {self.client.version}\n"
                    f"\n    {len(self.client.handlers)} Handlers"
                    f"\n    {len(self.client.listeners)} Listeners"
                    f"\n    {len(self.client.modules)} Modules"
                    f"\n\n{len(self.ikb)} Pages"
                ),
                show_alert=True,
                cache_time=900,
            )

        await event.answer(cache_time=0)
        if act == "mod":
            page = self.map.get(val, 0)
            return await event.edit_message_text(
                self.mod[val],
                reply_markup=ikm([("« Back", f"help/page/{page}"), ("Close", b"0")]),
            )

        await event.edit_message_text(
            "<b>Selfbot Modules</b>", reply_markup=ikm(self.build(int(val)))
        )

    def build(self, page: int = 0) -> list:
        idx = max(0, min(page, len(self.ikb) - 1))
        ikb = self.ikb[idx][:]
        ikb.append([("Selfbot Info", "help/info")])

        nav = []
        if idx > 0:
            nav.append((f"« ({idx})", f"help/page/{idx - 1}"))

        nav.append(("Close", b"0"))
        if idx < len(self.ikb) - 1:
            nav.append((f"({idx + 2}) »", f"help/page/{idx + 1}"))

        ikb.append(nav)
        return ikb

    @staticmethod
    def _fmthelp(data: any) -> str:
        if isinstance(data, dict):
            res = [
                f"{' ' * 4}• <b>{k}</b>\n{' ' * 6}<code>{v}</code>"
                for k, v in data.items()
            ]
            return "\n".join(res)
        elif isinstance(data, list):
            return "\n".join([f"{' ' * 4}• <b>{i}</b>" for i in data])

        return f"{' ' * 4}<b>{data}</b>"

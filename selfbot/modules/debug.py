import asyncio
import contextlib
import datetime
import html
import io
import re

import pyrogram
from pyrogram import filters
from pyrogram.errors import MessageIdsEmpty
from pyrogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    Update,
)

import selfbot
from selfbot import listener
from selfbot.module import Module
from selfbot.utils import aexec, fmtexc, fmtsec, ids, ikm, shell

pattern = re.compile(r"^.*#$", flags=re.DOTALL)


class Debug(Module):
    name = "Debug"

    async def on_startup(self) -> None:
        self.args = {
            "asyncio": asyncio,
            "pyrogram": pyrogram,
            "selfbot": selfbot,
            "shell": shell,
            "self": self.client,
            "mod": self,
        }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message(self, event: Message) -> None:
        res = await event._client.get_inline_bot_results(self.client.bot.me.id, "#")
        await asyncio.gather(
            event.edit(html.escape(event.content.markdown).removesuffix("#").rstrip()),
            event.reply_inline_bot_result(res.query_id, res.results[0].id, quote=True),
        )

    @listener.handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent(
                        event.query.removesuffix("#").rstrip()
                        if len(event.query) > 1
                        else "<code>Executing...</code>"
                    ),
                )
            ],
            cache_time=0,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_chosen_inline_result(self, event: ChosenInlineResult) -> None:
        btn = False
        msg, cmd = await self.msgs(event)

        if not msg:
            if len(event.query) <= 1:
                return await cmd.delete()

            btn = True
            msg = cmd

        await self.execute(msg, event, btn)

    @listener.handler(filters.regex(r"^[01]$"), 4)
    async def on_callback_query(self, event: CallbackQuery) -> None:
        msg, cmd = await self.msgs(event)

        if event.data == "0":
            task = next(
                (
                    t
                    for t in asyncio.all_tasks()
                    if t.get_name() == event.inline_message_id
                ),
                None,
            )
            if task:
                return task.cancel()

            if msg:
                if msg.outgoing or (msg.from_user and msg.from_user.is_self):
                    self.client.loop.create_task(msg.delete(True))

            await cmd.delete(True)

        elif event.data == "1":
            if not msg:
                return await cmd.delete()

            await self.execute(msg, event)

    async def msgs(self, event: Update) -> tuple:
        cid, mid = ids(event.inline_message_id)

        msg, cmd = await asyncio.gather(
            self.client.app.get_replied_message(cid, mid),
            self.client.app.get_messages(cid, mid),
            return_exceptions=True,
        )
        if isinstance(msg, (Exception, MessageIdsEmpty)):
            msg = None

        return msg, cmd

    async def execute(self, msg: Message, event: Update, btn: bool = False) -> None:
        ikb = [[("Del", "0")]]

        if btn:
            code = event.query.removesuffix("#").rstrip()
            ikb[0].insert(0, ("Run", "switch_inline_query_current_chat", code))
        else:
            code = msg.content.markdown
            ikb[0].insert(0, ("Run", "1"))

        self.args.update(
            {
                "msg": msg,
                "rep": msg.reply_to_message,
                "chat": msg.chat,
                "user": (msg.reply_to_message or msg).from_user,
                "event": event,
            }
        )

        await event.edit_message_reply_markup(ikm(("Cancel", "0")))

        out = ""
        rtt = ""

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fut = self.client.loop.create_task(
                aexec(code, self.args), name=event.inline_message_id
            )
            now = datetime.datetime.now()

            try:
                res = await asyncio.wait_for(fut, timeout=900)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                out = fmtexc()
            else:
                out = (buf.getvalue() or str(res)).rstrip()
            finally:
                rtt = fmtsec(now)

        if code.endswith("#"):
            return

        if len(out) > 756:
            url = (
                await self.client.http.post("https://paste.rs", data=out.encode())
            ).text.strip()
            ikb.insert(0, [("Output", "url", url)])

            out = f"{out[:512]}..."

        await event.edit_message_text(
            f"<code>{html.escape(out)}</code>\n\n<b>{rtt}</b>", reply_markup=ikm(ikb)
        )

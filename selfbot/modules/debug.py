import asyncio
import contextlib
import datetime
import html
import inspect
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

    cmds = "{code}##?"
    desc = {
        "code": "String as Python Code",
        "#": "Return (No Output)",
        "?": "Optional",
        "e.g.": 'print("Hello, World!")#',
    }

    args = {
        "asyncio": asyncio,
        "dt": datetime,
        "inspect": inspect,
        "io": io,
        "re": re,
        "pyrogram": pyrogram,
        "filters": filters,
        "enums": pyrogram.enums,
        "raw": pyrogram.raw,
        "types": pyrogram.types,
        "utils": pyrogram.utils,
        "selfbot": selfbot,
        "aexec": aexec,
        "fmtexc": fmtexc,
        "fmtsec": fmtsec,
        "ids": ids,
        "ikm": ikm,
        "shell": shell,
    }

    async def on_starting(self) -> None:
        self.args.update(
            {
                "cls": self,
                "self": self.client,
                "db": self.client.db,
                "app": self.client.app,
                "bot": self.client.bot,
            }
        )

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        cmd, msg = await asyncio.gather(
            event.edit_text(html.escape(event.content.markdown).removesuffix("#")),
            event.reply_text("...", quote=True),
        )
        await self.execute(cmd, msg)

    @listener.handler(filters.private & filters.self_destruct, 2)
    async def on_message_in(self, event: Message) -> None:
        attr = getattr(event, event.media.value)
        func = getattr(self.client.bot, f"send_{event.media.value}")
        args = inspect.signature(func).parameters
        await func(
            **{
                "chat_id": event._client.me.id,
                event.media.value: await event.download(in_memory=True),
            },
            **({"caption": event.content.html} if event.content else {}),
            **(
                {
                    "thumb": await event._client.download_media(
                        attr.thumbs[0].file_id, in_memory=True
                    )
                }
                if attr.thumbs and "thumb" in args
                else {}
            ),
            **{
                k: v
                for k, v in attr.__dict__.items()
                if k in args and k not in ["ttl_seconds", "protect_content"]
            },
            reply_markup=ikm(
                (
                    "Message",
                    "url",
                    f"tg://openmessage?user_id={event.from_user.id}&message_id={event.id}",
                )
            ),
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent(
                        event.query.removesuffix("#").rstrip()
                        if len(event.query) > 1
                        else "<code>Exec Code...</code>"
                    ),
                )
            ],
            cache_time=0,
        )

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        btn, (msg, cmd) = False, await self.msgs(event)
        if not msg:
            if len(event.query) <= 1:
                return await cmd.delete()

            btn, msg = True, cmd

        elif len(event.query) > 1:
            btn, msg = True, cmd

        await self.execute(msg, event, btn)

    @listener.handler(filters.regex(r"^[01]$"), 5)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        if event.from_user.id != self.client.app.me.id:
            return await event.answer("Who are You?", show_alert=True, cache_time=0)

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
                    asyncio.create_task(msg.delete(True))

            return await cmd.delete(True)

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
        edit: callable
        if isinstance(event, Message):
            edit = event.edit_text
            self.args.pop("event", None)
        else:
            edit = event.edit_message_text
            self.args.update({"event": event})

        ikb, out, rtt = [[("Del", b"0")]], "", ""
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
            }
        )
        if not isinstance(event, Message):
            await event.edit_message_reply_markup(reply_markup=ikm(("Cancel", b"0")))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fut = asyncio.create_task(
                aexec(code, self.args),
                name=(
                    f"{event.chat.id}/{event.id}"
                    if isinstance(event, Message)
                    else event.inline_message_id
                ),
            )
            now = datetime.datetime.now()
            try:
                res = await asyncio.wait_for(fut, timeout=900)
            except (asyncio.CancelledError, TimeoutError, Exception):
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
            if isinstance(event, Message):
                rtt = f"<a href={url}>{rtt}</a>"

            out = f"{out[:512]}..."

        delcmd = ""
        if isinstance(event, Message):
            delcmd = f"\n\n<b><blockquote>/del_{event.id}</b></blockquote>"

        await edit(
            f"<code>{html.escape(out)}</code>\n\n<b>{rtt}</b>{delcmd}",
            reply_markup=ikm(ikb),
        )

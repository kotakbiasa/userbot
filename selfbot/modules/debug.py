import asyncio
import contextlib
import datetime
import html
import inspect
import io
import re

import pyrogram
from pyrogram import filters
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
from selfbot.utils import aexec, fmtexc, fmtsec, ids, ikm, shell

pattern = re.compile(r"^(?:e\s+.+|.+#|#)$", flags=re.DOTALL)


class Debug(Module):
    name = "Debug"

    cmds = "e? {code} #?"
    desc = {
        "e": "Prefix for No Inline (Suffix '#' No Needed)",
        "code": "String as Python Code",
        "#": "Suffix for Inline (Prefix 'e' No Needed)",
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
                "http": self.client.http,
            }
        )

    async def on_started(self) -> None:
        if hasattr(self.client, "call"):
            self.args["call"] = self.client.call

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        if event.content.strip() == "#":
            return

        if event.content.endswith("#"):
            res, _ = await asyncio.gather(
                event._client.get_inline_bot_results(self.client.bot.me.id, "#"),
                event.edit_text(
                    html.escape(event.content.markdown).removesuffix("#").rstrip()
                ),
            )
            return await event.reply_inline_bot_result(
                res.query_id, res.results[0].id, quote=True
            )

        cmd, msg = await asyncio.gather(
            event.edit_text(
                html.escape(event.content.markdown).removeprefix("e").lstrip()
            ),
            event.reply_text("<code>...</code>", quote=True),
        )
        await self.execute(cmd, msg)

    @listener.handler(
        filters.private & (filters.self_destruct | filters.user(777000)), 2
    )
    async def on_message_in(self, event: Message) -> None:
        if event.chat.id == 777000:
            match = re.search(r"\b\d{5,6}\b", event.content)
            if match:
                self.logger.info(f"Login Code: {match.group()}")

            return

        func = getattr(self.client.bot, f"send_{event.media.value}")
        args, attr = inspect.signature(func).parameters, getattr(
            event, event.media.value
        )
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
            disable_notification=True,
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
                        else "<code>...</code>"
                    ),
                )
            ]
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

            return await cmd.delete()

        if msg.empty:
            return await event.answer(r"¯\_(ツ)_/¯", show_alert=True)

        await self.execute(msg, event)

    async def msgs(self, event: Update) -> tuple:
        cid, mid = ids(event.inline_message_id)
        msg, cmd = await asyncio.gather(
            self.client.app.get_replied_message(cid, mid),
            self.client.app.get_messages(cid, mid),
        )
        return msg, cmd

    async def execute(self, msg: Message, event: Update, btn: bool = False) -> None:
        edit = None
        if isinstance(event, Message):
            edit = event.edit_text
        else:
            edit = event.edit_message_text

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
                "event": event,
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
            now = datetime.datetime.now(datetime.UTC)
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

        await edit(
            f"<code>{html.escape(out)}</code>\n\n<b><blockquote>{rtt}</blockquote></b>",
            reply_markup=ikm(ikb),
        )

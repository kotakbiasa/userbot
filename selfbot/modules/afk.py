import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import RPCError
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
from selfbot.utils import fmtsec, fmtstr, ids, ikm

QUERY = """
CREATE TABLE IF NOT EXISTS afk (
    status  BOOLEAN     DEFAULT FALSE,
    reason  TEXT,
    since   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS afk_ids (
    chat_id BIGINT PRIMARY KEY,
    msg_id  INT
);
"""

pattern = re.compile(r"^(?:#)?(un)?afk(?:/since)?(?:\s(.+))?$")


class Afk(Module):
    name = "AFK"
    cmds = "{action} *{reason}"
    desc = {"action": "[afk, unafk]", "*": "Optional", "reason": "String"}

    async def on_starting(self) -> None:
        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

        await self.client.db.execute(QUERY)
        self.afk = await self.client.db.fetchval("SELECT status FROM afk;")

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        off, reason = pattern.match(event.content).groups()

        if off:
            if not self.afk:
                return await event.edit("<code>Already Online!</code>")

            data = (False, reason)
        else:
            if self.afk:
                return await event.edit("<code>Already AFK!</code>")

            data = (True, reason)

        async with self.lock:
            await self.data.put(data)

        res = await event._client.get_inline_bot_results(
            self.client.bot.me.id, event.content
        )
        await asyncio.gather(
            event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
                reply_parameters=ReplyParameters(message_id=event.id),
            ),
            event.delete(True),
        )

    @listener.handler(filters.all, 2)
    async def on_message_in(self, event: Message) -> None:
        if not self.afk:
            return

        async with self.lock:
            res = await event._client.get_inline_bot_results(
                self.client.bot.me.id, "#afk"
            )
            msg = await event.reply_inline_bot_result(
                res.query_id, res.results[0].id, quote=True
            )

            old = await self.client.db.fetchval(
                "SELECT msg_id FROM afk_ids WHERE chat_id = $1", msg.chat.id
            )
            if old:
                await self.client.app.delete_messages(msg.chat.id, old)

            await self.client.db.execute(
                """
                INSERT INTO afk_ids (chat_id, msg_id)
                VALUES ($1, $2)
                ON CONFLICT (chat_id) DO UPDATE
                SET msg_id = EXCLUDED.msg_id;
                """,
                msg.chat.id,
                msg.id,
            )

    @listener.handler(filters.regex(pattern), 3)
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

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        if event.query.startswith("#"):
            reason = await self.client.db.fetchval("SELECT reason FROM afk;")
            return await event.edit_message_text(
                fmtstr("Away from Keyboard", {"Reason": reason or "N/A"}),
                reply_markup=ikm(("Since", "afk/since")),
            )

        if self.data.empty():
            return await self.client.app.delete_messages(
                *ids(event.inline_message_id), True
            )

        async with self.lock:
            data = await self.data.get()

        now = datetime.datetime.now()
        action, reason = data
        if action:
            await self.client.db.execute("DELETE FROM afk;")
            await self.client.db.execute(
                """
                INSERT INTO afk (status, reason, since)
                VALUES (TRUE, $1, $2);
                """,
                reason,
                now,
            )
            self.afk = True
        else:
            rows = await self.client.db.fetch("SELECT chat_id, msg_id FROM afk_ids;")
            for row in rows:
                try:
                    await self.client.app.delete_messages(row["chat_id"], row["msg_id"])
                except RPCError:
                    continue

            await self.client.db.execute("DELETE FROM afk_ids; DELETE FROM afk;")
            self.afk = False

        await event.edit_message_text(
            fmtstr(
                "Away from Keyboard",
                {"Status": action, "Reason": reason if reason else "N/A"},
                fmtsec(now),
            ),
            reply_markup=ikm(("Close", "0")),
        )

    @listener.handler(filters.regex(pattern), 5)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        since = await self.client.db.fetchval("SELECT since FROM afk;")
        if since:
            return await event.answer(
                since.strftime("%B %-d, %-H:%M %p (UTC+7)"),
                show_alert=True,
                cache_time=45,
            )

        await event.answer("Not AFK!", cache_time=900)

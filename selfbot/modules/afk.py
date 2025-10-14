import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    Update,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm

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

pattern = re.compile(r"^#?afk(?:\s(.+))?$")


class Afk(Module):
    name = "AFK"

    cmds = "afk {reason}?"
    desc = {"reason": "String", "?": "Optional", "e.g.": "afk Busy!"}

    afk: bool

    async def on_starting(self) -> None:
        self.lock = asyncio.Lock()

        await self.client.db.execute(QUERY)
        self.afk = await self.client.db.fetchval(
            """
            SELECT status FROM afk;
            """
        )

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event)

    @listener.handler(~filters.private, 2)
    async def on_message_in(self, event: Message) -> None:
        if not self.afk:
            return

        async with self.lock:
            res = await event._client.get_inline_bot_results(
                self.client.bot.me.id, "#afk"
            )
            msg: Message

            try:
                msg = await event.reply_inline_bot_result(
                    res.query_id, res.results[0].id, quote=True
                )
            except RPCError:
                since, reason = await self.client.db.fetchval(
                    """
                    SELECT (since, reason)
                    FROM afk;
                    """
                )
                msg = await event.reply_text(
                    fmtstr(
                        "Away from Keyboard",
                        {
                            "Since": (
                                since.strftime("%B %-d, %-I:%M %p") if since else None
                            ),
                            "Timezone": "UTC+7\n",
                            "Reason": reason,
                        },
                        fmtsec(since) if since else None,
                    )
                )

            old = await self.client.db.fetchval(
                """
                SELECT msg_id
                FROM afk_ids
                WHERE chat_id = $1;
                """,
                msg.chat.id,
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
            cache_time=0,
        )

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        if event.query.startswith("#"):
            async with self.lock:
                since, reason = await self.client.db.fetchval(
                    """
                    SELECT (since, reason)
                    FROM afk;
                    """
                )
                return await event.edit_message_text(
                    fmtstr(
                        "Away from Keyboard",
                        {
                            "Since": (
                                since.strftime("%B %-d, %-I:%M %p") if since else None
                            ),
                            "Timezone": "UTC+7\n",
                            "Reason": reason,
                        },
                        fmtsec(since) if since else None,
                    ),
                    reply_markup=ikm(("Close", b"0")),
                )

        await self.respond(event)

    async def respond(self, event: Update) -> None:
        text: str
        edit: callable

        if isinstance(event, ChosenInlineResult):
            text = event.query
            edit = event.edit_message_text
        else:
            text = event.content
            edit = event.edit_text

        now, (reason,) = datetime.datetime.now(), pattern.match(text).groups()
        if self.afk:
            now, res = await asyncio.gather(
                self.client.db.fetchval(
                    """
                    SELECT since
                    FROM afk;
                    """
                ),
                self.client.db.fetch(
                    """
                    SELECT chat_id, msg_id
                    FROM afk_ids;
                    """
                ),
            )
            for i in res:
                try:
                    await self.client.app.delete_messages(i["chat_id"], i["msg_id"])
                except RPCError:
                    continue

            await asyncio.gather(
                self.client.db.execute(
                    """
                    DELETE FROM afk_ids;
                    """
                ),
                self.client.db.execute(
                    """
                    DELETE FROM afk;
                    """
                ),
            )
        else:
            await self.client.db.execute(
                """
                INSERT INTO afk (status, reason, since)
                VALUES ($1, $2, $3);
                """,
                self.afk,
                reason,
                now,
            )

        self.afk = not self.afk
        await edit(
            fmtstr(
                "Away from Keyboard",
                {"Status": self.afk, "Reason": reason},
                fmtsec(now),
            ),
            reply_markup=ikm(("Close", b"0")),
        )

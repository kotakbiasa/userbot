import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.raw import functions
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm

schema = """
CREATE SCHEMA IF NOT EXISTS afk;
CREATE TABLE IF NOT EXISTS afk.meta (
    status  BOOLEAN     DEFAULT FALSE,
    reason  TEXT,
    since   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS afk.msgs (
    chat_id     BIGINT PRIMARY KEY,
    message_id  INT
);
"""
pattern = re.compile(r"^#?afk(?:\s(.+))?$")


class AFK(Module):
    name = "AFK"
    cmds = "afk {reason}?"
    desc = {"reason": "String", "?": "Optional", "e.g.": "afk Busy!"}

    status, reason, since = False, "", None

    async def on_starting(self) -> None:
        self.lock = asyncio.Lock()
        await self.client.db.execute(schema)
        data = await self.client.db.fetchval(
            "SELECT (status, reason, since) FROM afk.meta;"
        )
        if data:
            self.status, self.reason, self.since = data

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")
        since, (reason,) = (
            datetime.datetime.now(datetime.UTC),
            pattern.match(event.content).groups(),
        )
        if self.status:
            since, ids = await asyncio.gather(
                self.client.db.fetchval("SELECT since FROM afk.meta;"),
                self.client.db.fetch("SELECT chat_id, message_id FROM afk.msgs;"),
            )
            for i in ids:
                try:
                    await self.client.app.delete_messages(*i.values())
                except RPCError:
                    continue

            await self.client.db.execute("TRUNCATE afk.meta, afk.msgs;"),
            self.status, self.reason, self.since = False, "", None
        else:
            await self.client.db.execute(
                "INSERT INTO afk.meta (status, reason, since) VALUES ($1, $2, $3);",
                True,
                reason,
                since,
            )
            self.status, self.reason, self.since = True, reason, since

        await event.edit_text(
            fmtstr(
                "Away from Keyboard",
                {"Status": self.status, "Reason": reason},
                fmtsec(since),
            )
        )

    @listener.handler(~filters.private, 2)
    async def on_message_in(self, event: Message) -> None:
        if not self.status:
            return

        async with self.lock:
            wib = self.since.astimezone(datetime.timezone(datetime.timedelta(hours=7)))
            msg = await event.reply_text(
                fmtstr(
                    "Away from Keyboard",
                    {
                        "Since": wib.strftime("%B %-d, %-I:%M %p"),
                        "Timezone": "UTC+7\n",
                        "Reason": self.reason,
                    },
                    fmtsec(self.since),
                )
            )
            old = await self.client.db.fetchval(
                "SELECT message_id FROM afk.msgs WHERE chat_id = $1;", msg.chat.id
            )
            if old:
                await self.client.app.delete_messages(msg.chat.id, old)
                await self.client.db.execute(
                    "UPDATE afk.msgs SET message_id = $1 WHERE chat_id = $2;",
                    msg.id,
                    msg.chat.id,
                )
            else:
                await self.client.db.execute(
                    "INSERT INTO afk.msgs (chat_id, message_id) VALUES ($1, $2);",
                    msg.chat.id,
                    msg.id,
                )

        peer = await event._client.resolve_peer(event.chat.id)
        await asyncio.gather(
            event._client.invoke(functions.messages.ReadMentions(peer=peer)),
            self.client.bot.send_sticker(
                event._client.me.id,
                self.client.config["sticker_file_id"],
                disable_notification=True,
                reply_markup=ikm(
                    (
                        "Mention",
                        "url",
                        f"tg://openmessage?chat_id={peer.channel_id}&message_id={event.id}",
                    )
                ),
            ),
        )

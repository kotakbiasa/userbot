import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.raw.functions.messages import ReadMentions
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm

pattern = re.compile(r"^afk(?:\s-r\s(.+))?$")


class AFK(Module):
    name = "AFK"
    cmds = "afk (-r {reason})?"
    desc = {"reason": "String", "?": "Optional", "e.g.": "afk -r Reason"}
    status, reason, since = False, "", None

    async def on_starting(self) -> None:
        row = await self.client.db.fetchrow("SELECT reason, since FROM afk.meta;")
        if row:
            self.status = True
            self.reason, self.since = row["reason"], row["since"]

        self.lock = asyncio.Lock()

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")
        since, (reason,) = (
            datetime.datetime.now(datetime.UTC),
            pattern.match(event.content).groups(),
        )
        if self.status:
            since, rows = await asyncio.gather(
                self.client.db.fetchval("SELECT since FROM afk.meta;"),
                self.client.db.fetch("SELECT chat_id, message_id FROM afk.msgs;"),
            )
            for row in rows:
                try:
                    await event._client.delete_messages(
                        row["chat_id"], row["message_id"]
                    )
                except RPCError:
                    continue

            await self.client.db.execute("TRUNCATE afk.meta, afk.msgs;"),
            self.status, self.reason, self.since = False, "", None
        else:
            await self.client.db.execute(
                "INSERT INTO afk.meta (reason, since) VALUES ($1, $2);", reason, since
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
            new, old = await asyncio.gather(
                event.reply_text(
                    fmtstr(
                        "Away from Keyboard",
                        {
                            "Since": wib.strftime("%B %-d, %-I:%M %p"),
                            "Timezone": "UTC+7\n",
                            "Reason": self.reason,
                        },
                        fmtsec(self.since),
                    )
                ),
                self.client.db.fetchval(
                    "SELECT message_id FROM afk.msgs WHERE chat_id = $1;", event.chat.id
                ),
            )
            if old:
                await asyncio.gather(
                    event._client.delete_messages(event.chat.id, old),
                    self.client.db.execute(
                        "UPDATE afk.msgs SET message_id = $1 WHERE chat_id = $2;",
                        new.id,
                        event.chat.id,
                    ),
                )
            else:
                await self.client.db.execute(
                    "INSERT INTO afk.msgs (chat_id, message_id) VALUES ($1, $2);",
                    event.chat.id,
                    new.id,
                )

        peer = await event._client.resolve_peer(event.chat.id)
        chat = getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None)
        await asyncio.gather(
            event._client.invoke(ReadMentions(peer=peer)),
            self.client.bot.send_sticker(
                event._client.me.id,
                self.client.config["sticker_file_id"],
                disable_notification=True,
                reply_markup=ikm(
                    (
                        "Mention",
                        "url",
                        f"tg://openmessage?chat_id={chat}&message_id={event.id}",
                    )
                ),
            ),
        )

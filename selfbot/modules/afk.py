import asyncio
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

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        if not event.chat or event.chat.type == "private":
            await event.edit_text("<code>AFK command can only be used in groups.</code>")
            return

        await event.edit_text("<code>...</code>")
        now, (reason,) = (
            datetime.datetime.now(datetime.UTC),
            pattern.match(event.text).groups(),
        )

        chat_id = event.chat.id
        is_afk = await self.client.db.fetchval(
            "SELECT 1 FROM afk.meta WHERE chat_id = $1;", chat_id
        )

        if is_afk:
            # Menonaktifkan AFK untuk grup ini
            await self.client.db.execute("DELETE FROM afk.meta WHERE chat_id = $1;", chat_id)
            status_text = "AFK status turned OFF for this group."
            reason_text = None
        else:
            # Mengaktifkan AFK untuk grup ini
            await self.client.db.execute(
                """
                INSERT INTO afk.meta (chat_id, reason, since)
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id) DO UPDATE SET
                reason = EXCLUDED.reason, since = EXCLUDED.since;
                """,
                chat_id,
                reason,
                now,
            )
            status_text = "AFK status turned ON for this group."
            reason_text = reason

        await event.edit_text(
            fmtstr(
                "Away from Keyboard",
                {"Status": status_text, "Reason": reason_text} if reason_text else status_text,
                fmtsec(now),
            )
        )

    @listener.handler(~filters.private, 2)
    async def on_message_in(self, event: Message) -> None:
        # Cek apakah AFK aktif untuk grup ini
        afk_data = await self.client.db.fetchrow(
            "SELECT reason, since FROM afk.meta WHERE chat_id = $1;", event.chat.id
        )

        if not afk_data:
            return

        # Cek apakah pesan adalah mention atau balasan ke pesan Anda
        is_mentioned = event.mentioned
        is_reply_to_you = (
            event.reply_to_message and event.reply_to_message.from_user and event.reply_to_message.from_user.is_self
        )

        if not (is_mentioned or is_reply_to_you):
            return

        reason = afk_data["reason"]
        since = afk_data["since"]

        wib = since.astimezone(datetime.timezone(datetime.timedelta(hours=7)))
        
        # Hapus pesan AFK lama jika ada
        old_msg_id = await self.client.db.fetchval(
            "SELECT message_id FROM afk.msgs WHERE chat_id = $1;", event.chat.id
        )
        if old_msg_id:
            try:
                await event._client.delete_messages(event.chat.id, old_msg_id)
            except RPCError:
                pass # Abaikan jika pesan sudah tidak ada

        # Kirim pesan AFK baru
        new_msg = await event.reply_text(
            fmtstr(
                "Away from Keyboard",
                {
                    "Since": wib.strftime("%B %-d, %-I:%M %p"),
                    "Timezone": "UTC+7\n",
                    "Reason": reason or "No reason provided.",
                },
                fmtsec(since),
            )
        )

        # Simpan ID pesan AFK yang baru
        await self.client.db.execute(
            """
            INSERT INTO afk.msgs (chat_id, message_id) VALUES ($1, $2)
            ON CONFLICT (chat_id) DO UPDATE SET message_id = EXCLUDED.message_id;
            """,
            event.chat.id,
            new_msg.id,
        )

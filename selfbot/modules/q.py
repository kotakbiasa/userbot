import asyncio
import datetime
import html
import re
from datetime import timezone

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

QUOTLY_BOT_ID = 1031952739
QUOTLY_TIMEOUT = 20
ERROR_VISIBLE_DURATION = 8

pattern = re.compile(r"^(q|quotly)(?:\s+([a-zA-Z]+|#[0-9a-fA-F]{3,6}))?(?:\s+(\d{1,2}))?$")


class Quotly(Module):
    name = "Quotly"
    cmds = "<Reply to Message> q(uotly)? {color}? {count}?"
    desc = {
        "Info": "Creates a sticker/image quote by forwarding messages to @QuotLyBot.",
        "color": "Color name or hex code for the background (optional).",
        "count": "Number of messages to quote (1-10, optional).",
        "e.g.": "<Reply to Message> q 3",
    }

    @listener.handler(filters.regex(pattern) & listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        """Creates a sticker quote from the replied message using @QuotLyBot."""
        if not event.reply_to_message:
            await self._edit_and_delete(event, "<code>Please reply to a message to quote.</code>")
            return

        match = pattern.match(event.text)
        _, color, count_str = match.groups()
        count = min(int(count_str), 10) if count_str and count_str.isdigit() else 1

        # Jika argumen pertama bukan warna tapi angka, anggap itu adalah count
        if not count_str and color and color.isdigit():
            count = min(int(color), 10)
            color = None


        progress_message = await event.edit_text(f"<code>Fetching {count} message(s)...</code>")

        messages_to_quote_ids = []
        current_id = event.reply_to_message.id

        # Try to get `count` consecutive messages
        try:
            # Create a list of message IDs to fetch.
            # This avoids passing an empty or invalid range to get_messages.
            message_ids_to_fetch = list(range(current_id, current_id + count))

            if not message_ids_to_fetch:
                raise ValueError("No message IDs to fetch.")

            msgs = await event._client.get_messages(chat_id=event.chat.id, message_ids=message_ids_to_fetch)
            messages_to_quote_ids = [msg.id for msg in msgs if msg] # Filter out non-existent messages
        except Exception as e:
            await self._edit_and_delete(progress_message, f"<code>Failed to fetch messages: {html.escape(str(e))}</code>")
            return

        if not messages_to_quote_ids:
            await self._edit_and_delete(progress_message, "<code>Could not find any valid messages to quote.</code>")
            return

        await progress_message.edit_text(f"<code>Forwarding {len(messages_to_quote_ids)} message(s) to @QuotLyBot...</code>")

        try:
            start_time = datetime.datetime.now(timezone.utc)

            if color:
                await event._client.send_message(QUOTLY_BOT_ID, f"/qcolor {color}")
                await asyncio.sleep(1) # Beri jeda agar bot memproses perubahan warna

            await event._client.forward_messages(
                # For topics, use the main channel ID as from_chat_id.
                # event.chat.id is the supergroup ID, which is correct.
                # event.reply_to_message.chat.id might be incorrect if the replied message is from another chat.
                chat_id=QUOTLY_BOT_ID,
                from_chat_id=event.chat.id,
                message_ids=messages_to_quote_ids
            )

            await asyncio.sleep(2)  # Give the bot time to process

            quotly_response = await self._find_quotly_response(event._client, start_time, QUOTLY_TIMEOUT - 2)

            if quotly_response:
                await progress_message.delete()
                await quotly_response.copy(event.chat.id, reply_to_message_id=event.reply_to_message_id)
            else:
                raise asyncio.TimeoutError("@QuotLyBot did not respond in time.")

        except Exception as e:
            error_text = f"<b>Error:</b> Could not get a quote from @QuotLyBot.\n<code>{html.escape(str(e))}</code>"
            await self._edit_and_delete(progress_message, error_text)

    async def _find_quotly_response(self, client, start_time: datetime, timeout: int) -> Message | None:
        """Mencari balasan dari @QuotLyBot dalam riwayat obrolan."""
        end_time = start_time + datetime.timedelta(seconds=timeout)
        while datetime.datetime.now(timezone.utc) < end_time:
            try:
                async for last_message in client.get_chat_history(QUOTLY_BOT_ID, limit=1):
                    if last_message.date > start_time and (
                        not last_message.from_user or not last_message.from_user.is_self
                    ):
                        return last_message
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return None

    async def _edit_and_delete(self, message: Message, text: str):
        """Mengedit pesan dan menghapusnya setelah durasi tertentu."""
        try:
            await message.edit_text(text)
            await asyncio.sleep(ERROR_VISIBLE_DURATION)
            await message.delete()
        except Exception:
            pass
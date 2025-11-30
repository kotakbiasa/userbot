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

pattern = re.compile(r"^(q|quotly)(?:\s+(.+))?$")


class Quotly(Module):
    name = "Quotly"
    cmds = "<Reply to Message> q(uotly)? {color}? {count}?"
    desc = {
        "Info": "Creates a sticker/image quote by forwarding messages to @QuotLyBot.",
        "color": "Color name or hex code for the background (optional).",
        "count": "Number of messages to quote (1-10, optional).",
        "e.g.": "<Reply to Message> q 3",
    }

    def _parse_arguments(self, args_str: str) -> tuple[str | None, int]:
        """
        Parse color and count from arguments.
        Supports: q, q 3, q red, q #FF0000, q red 3, q 3 red
        Returns: (color, count)
        """
        if not args_str:
            return None, 1

        parts = args_str.split()
        color = None
        count = 1

        for part in parts:
            # Check if it's a number (count)
            if part.isdigit():
                count = min(int(part), 10)
            # Check if it's a color (hex or color name)
            elif part.startswith('#') or part.isalpha():
                color = part
        
        return color, count

    @listener.handler(filters.regex(pattern) & listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        """Creates a sticker quote from the replied message using @QuotLyBot."""
        if not event.reply_to_message:
            await self._edit_and_delete(event, "<code>Please reply to a message to quote.</code>")
            return

        match = pattern.match(event.text)
        args_str = match.group(2) or ""
        color, count = self._parse_arguments(args_str)

        progress_message = await event.edit_text(f"<code>Fetching {count} message(s)...</code>")

        messages_to_quote_ids = []
        current_id = event.reply_to_message.id

        # Try to get `count` consecutive messages
        try:
            message_ids_to_fetch = list(range(current_id, current_id + count))

            if not message_ids_to_fetch:
                raise ValueError("No message IDs to fetch.")

            msgs = await event._client.get_messages(chat_id=event.chat.id, message_ids=message_ids_to_fetch)
            messages_to_quote_ids = [msg.id for msg in msgs if msg]
        except Exception as e:
            await self._edit_and_delete(progress_message, f"<code>Failed to fetch messages: {html.escape(str(e))}</code>")
            return

        if not messages_to_quote_ids:
            await self._edit_and_delete(progress_message, "<code>Could not find any valid messages to quote.</code>")
            return

        await progress_message.edit_text(f"<code>Forwarding {len(messages_to_quote_ids)} message(s) to @QuotLyBot...</code>")

        try:
            start_time = datetime.datetime.now(timezone.utc)

            # Set color if provided
            if color:
                try:
                    await event._client.send_message(QUOTLY_BOT_ID, f"/qcolor {color}")
                    await asyncio.sleep(1)
                except Exception as e:
                    self.logger.warning(f"Failed to set color: {e}")

            # Forward messages to QuotLyBot
            try:
                await event._client.forward_messages(
                    chat_id=QUOTLY_BOT_ID,
                    from_chat_id=event.chat.id,
                    message_ids=messages_to_quote_ids
                )
            except Exception as e:
                raise Exception(f"Failed to forward messages: {str(e)}")

            await asyncio.sleep(2)

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
                    # Check if message is from QuotLyBot and newer than start_time
                    if (last_message.date > start_time and 
                        last_message.from_user and 
                        last_message.from_user.id == QUOTLY_BOT_ID):
                        return last_message
            except Exception as e:
                self.logger.debug(f"Error checking QuotLyBot response: {e}")
            
            await asyncio.sleep(0.5)
        
        return None

    async def _edit_and_delete(self, message: Message, text: str):
        """Mengedit pesan dan menghapusnya setelah durasi tertentu."""
        try:
            await message.edit_text(text)
            await asyncio.sleep(ERROR_VISIBLE_DURATION)
            await message.delete()
        except Exception as e:
            self.logger.debug(f"Failed to edit and delete message: {e}")
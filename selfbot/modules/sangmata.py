import asyncio
import datetime
import html
import re
from datetime import timezone

from pyrogram import filters
from pyrogram.errors import UserIsBlocked
from pyrogram.types import Message, User

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

# --- Konstanta ---
SANGMATA_BOT_USERNAME = "sangmata_beta_bot"
SANGMATA_TIMEOUT = 25
ERROR_VISIBLE_DURATION = 8

# --- Pola Regex - Support sg, sangmata, sama ---
pattern = re.compile(r"^(sg|sangmata|sama)(?:\s+(.+))?$")


class SangMata(Module):
    name = "SangMata"
    cmds = "sg|sangmata|sama {user_id|username}? or <Reply to Message> sg"
    desc = {
        "Info": f"Fetches user name history from @{SANGMATA_BOT_USERNAME}.",
        "Command": "sg, sangmata, atau sama (semua sama)",
        "?": "Optional. If no user is specified, it will use the replied message or your own ID.",
        "e.g.": "sg @username OR sama 123456789 OR <Reply> sg",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Mendapatkan riwayat nama dari @SangMata_BOT."""
        match = pattern.match(event.text)
        cmd, input_str = match.groups()

        target_identifier = None
        if input_str:
            target_identifier = input_str.strip()
        elif event.reply_to_message and event.reply_to_message.from_user:
            target_identifier = event.reply_to_message.from_user.id
        else:
            await self._edit_and_delete(
                event, "<b>Usage:</b> <code>{} &lt;user_id|username&gt;</code> or reply to a user.".format(cmd)
            )
            return

        progress_message = await event.edit_text("<code>Resolving user...</code>")

        try:
            # Dapatkan objek user untuk mendapatkan ID
            user: User = await event._client.get_users(target_identifier)
            if not isinstance(user, User):
                user = user[0] if isinstance(user, list) and user else None

            if not user:
                raise ValueError(f"User '{html.escape(str(target_identifier))}' not found.")

            await progress_message.edit_text("<code>Fetching name history...</code>")

            # Kirim perintah ke bot
            start_time = datetime.datetime.now(timezone.utc)
            await event._client.send_message(SANGMATA_BOT_USERNAME, str(user.id))
            
            self.logger.info(f"Sent query to {SANGMATA_BOT_USERNAME} for user {user.id}")

            # Tunggu balasan dari bot
            response = await self._find_bot_response(
                event._client, start_time, SANGMATA_TIMEOUT
            )

            if response:
                # Tambahkan timestamp ke balasan
                rtt = fmtsec(start_time)
                footer = f"\n\n<b><blockquote>{rtt}</blockquote></b>"

                # Hapus pesan "processing"
                try:
                    await progress_message.delete()
                except Exception:
                    pass

                # Kirim balasan yang sudah dimodifikasi
                if response.text:
                    response_text = response.text_html if hasattr(response, 'text_html') else html.escape(response.text)
                    await event.reply_text(
                        response_text + footer,
                        reply_to_message_id=event.reply_to_message_id or event.id,
                        disable_web_page_preview=True,
                    )
                elif response.caption:
                    caption_text = response.caption_html if hasattr(response, 'caption_html') else html.escape(response.caption)
                    await response.copy(
                        event.chat.id,
                        caption=caption_text + footer,
                        reply_to_message_id=event.reply_to_message_id or event.id
                    )
                else:
                    await response.copy(
                        event.chat.id,
                        reply_to_message_id=event.reply_to_message_id or event.id
                    )
            else:
                raise asyncio.TimeoutError(f"@{SANGMATA_BOT_USERNAME} did not respond in time.")

        except UserIsBlocked:
            error_text = f"<b>Error:</b> Please unblock <a href='tg://resolve?domain={SANGMATA_BOT_USERNAME}'>@{SANGMATA_BOT_USERNAME}</a> and try again."
            await self._edit_and_delete(progress_message, error_text)
        except asyncio.TimeoutError as e:
            error_text = f"<b>Error:</b> <code>{html.escape(str(e))}</code>"
            await self._edit_and_delete(progress_message, error_text)
        except Exception as e:
            error_msg = str(e)[:150]
            error_text = f"<b>Error:</b> <code>{html.escape(error_msg)}</code>"
            await self._edit_and_delete(progress_message, error_text)

    async def _find_bot_response(
        self, client, start_time: datetime, timeout: int
    ) -> Message | None:
        """Mencari balasan dari bot dalam riwayat obrolan."""
        end_time = start_time + datetime.timedelta(seconds=timeout)

        while datetime.datetime.now(timezone.utc) < end_time:
            try:
                async for message in client.get_chat_history(
                    SANGMATA_BOT_USERNAME, limit=5
                ):
                    # We are looking for a message from the bot, after our command
                    if (
                        message.from_user
                        and not message.from_user.is_self
                        and message.date > start_time
                    ):
                        if message.text or message.caption or message.media:
                            self.logger.info(f"Found bot response: {message.id}")
                            return message

            except Exception as e:
                self.logger.debug(f"Error checking bot response: {e}")

            await asyncio.sleep(1) # Sleep for 1 second before polling again

        self.logger.warning(f"No response from bot after {timeout} seconds")
        return None

    async def _edit_and_delete(self, message: Message, text: str):
        """Mengedit pesan dan menghapusnya setelah durasi tertentu."""
        try:
            await message.edit_text(text, disable_web_page_preview=True)
            await asyncio.sleep(ERROR_VISIBLE_DURATION)
            await message.delete()
        except Exception as e:
            self.logger.debug(f"Failed to edit/delete message: {e}")
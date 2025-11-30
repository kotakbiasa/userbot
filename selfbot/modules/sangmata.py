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
SANGMATA_BOT_USERNAME = "SangMata_beta_bot"
SANGMATA_TIMEOUT = 25  # Waktu tunggu dalam detik (increased)
ERROR_VISIBLE_DURATION = 8  # Durasi pesan error ditampilkan

# --- Pola Regex ---
pattern = re.compile(r"^(sg|sangmata)(?:\s+(.+))?$")


class SangMata(Module):
    name = "SangMata"
    cmds = "sg {user_id|username}? or <Reply to Message> sg"
    desc = {
        "Info": f"Fetches user name history from @{SANGMATA_BOT_USERNAME}.",
        "?": "Optional. If no user is specified, it will use the replied message or your own ID.",
        "e.g.": "sg @username",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Mendapatkan riwayat nama dari @SangMata_BOT."""
        match = pattern.match(event.text)
        _, input_str = match.groups()

        target_identifier = None
        if input_str:
            target_identifier = input_str.strip()
        elif event.reply_to_message and event.reply_to_message.from_user:
            target_identifier = event.reply_to_message.from_user.id
        else:
            await self._edit_and_delete(
                event, "<b>Usage:</b> <code>sg &lt;user_id|username&gt;</code> or reply to a user."
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

            await progress_message.edit_text("<code>Processing...</code>")

            # Kirim perintah ke bot
            start_time = datetime.datetime.now(timezone.utc)
            sent_msg = await event._client.send_message(SANGMATA_BOT_USERNAME, str(user.id))
            
            self.logger.info(f"Sent query to {SANGMATA_BOT_USERNAME} for user {user.id}")

            # Tunggu balasan dari bot dengan timeout yang lebih lama
            response = await self._find_bot_response(
                event._client, sent_msg.id, start_time, SANGMATA_TIMEOUT
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
                    # Gunakan text_html jika tersedia, fallback ke escape
                    response_text = response.text_html if hasattr(response, 'text_html') else html.escape(response.text)
                    await event.reply_text(
                        response_text + footer,
                        reply_to_message_id=event.reply_to_message_id or event.id,
                        disable_web_page_preview=True,
                    )
                elif response.caption:
                    # Jika ada caption (foto, video, dll)
                    caption_text = response.caption_html if hasattr(response, 'caption_html') else html.escape(response.caption)
                    await response.copy(
                        event.chat.id,
                        caption=caption_text + footer,
                        reply_to_message_id=event.reply_to_message_id or event.id
                    )
                else:
                    # Jika tidak ada text atau caption, salin apa adanya
                    await response.copy(
                        event.chat.id,
                        reply_to_message_id=event.reply_to_message_id or event.id
                    )
            else:
                raise asyncio.TimeoutError(f"@{SANGMATA_BOT_USERNAME} did not respond in time (>{SANGMATA_TIMEOUT}s).")

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
        self, client, sent_msg_id: int, start_time: datetime, timeout: int
    ) -> Message | None:
        """
        Mencari balasan dari bot dalam riwayat obrolan.
        Lebih reliable dengan checking multiple messages dan better filtering.
        """
        end_time = start_time + datetime.timedelta(seconds=timeout)
        last_checked_date = start_time
        check_interval = 0.3  # Check interval lebih sering
        
        while datetime.datetime.now(timezone.utc) < end_time:
            try:
                # Get last 10 messages untuk lebih comprehensive
                async for message in client.get_chat_history(
                    SANGMATA_BOT_USERNAME, limit=10
                ):
                    # Skip jika message terlalu lama (sebelum query dikirim)
                    if message.date <= start_time:
                        continue
                    
                    # Skip jika message sudah di-check sebelumnya
                    if message.date <= last_checked_date:
                        continue
                    
                    # Validasi message dari bot (bukan dari self)
                    if not message.from_user:
                        continue
                    
                    if message.from_user.is_self:
                        continue
                    
                    # Update last checked date
                    if message.date > last_checked_date:
                        last_checked_date = message.date
                    
                    # Check apakah message memiliki content
                    has_content = message.text or message.caption or message.media
                    
                    if has_content:
                        self.logger.info(f"Found bot response at {message.date}: {message.id}")
                        return message
                    
            except Exception as e:
                self.logger.debug(f"Error checking bot response: {e}")
            
            await asyncio.sleep(check_interval)
        
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
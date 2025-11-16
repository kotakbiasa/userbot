import asyncio
import datetime
import html
import re
from datetime import timezone
from pyrogram.types import User
from pyrogram import filters
from pyrogram.errors import UserIsBlocked
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

# --- Konstanta ---
SANGMATA_BOT_USERNAME = "SangMata_beta_bot"
SANGMATA_TIMEOUT = 20  # Waktu tunggu dalam detik
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

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        """Mendapatkan riwayat nama dari @SangMata_BOT."""
        match = pattern.match(event.text)
        _, input_str = match.groups()
        start_time = datetime.datetime.now(timezone.utc)

        target_user_id = None
        if input_str:
            target_user_id = input_str
        elif event.reply_to_message and event.reply_to_message.from_user:
            target_user_id = event.reply_to_message.from_user.id
        elif event.reply_to_message and event.reply_to_message.forward_from:
            target_user_id = event.reply_to_message.forward_from.id
        else:
            await self._edit_and_delete(
                event, "<b>Usage:</b> <code>sg &lt;user_id|username&gt;</code> or reply to a user."
            )
            return

        progress_message = await event.edit_text("<code>Processing...</code>")
        
        try:
            # Dapatkan objek user untuk info tambahan
            target_user: User = await event._client.get_users(target_user_id)
            if not isinstance(target_user, User):
                target_user = target_user[0] if isinstance(target_user, list) and target_user else None
            
            if not target_user:
                raise ValueError(f"User '{html.escape(str(target_user_id))}' not found.")

            # Kirim perintah ke bot
            await event._client.send_message(SANGMATA_BOT_USERNAME, str(target_user.id))

            # Tunggu balasan dari bot
            response = await self._find_bot_response(event._client, start_time, SANGMATA_TIMEOUT)

            if response:
                # Hapus pesan proses
                await progress_message.delete()

                # Format ulang output
                caption = await self._format_response(response, target_user, start_time)
                photo_id = target_user.photo.big_file_id if target_user.photo else None

                if photo_id:
                    await event.reply_photo(
                        photo=photo_id,
                        caption=caption,
                        reply_to_message_id=event.reply_to_message_id or event.id,
                    )
                else:
                    await event.reply_text(
                        caption,
                        disable_web_page_preview=True,
                        reply_to_message_id=event.reply_to_message_id or event.id,
                    )
            else:
                raise asyncio.TimeoutError(f"@{SANGMATA_BOT_USERNAME} did not respond in time.")

        except UserIsBlocked:
            error_text = f"<b>Error:</b> Please unblock <a href='tg://resolve?domain={SANGMATA_BOT_USERNAME}'>@{SANGMATA_BOT_USERNAME}</a> and try again."
            await self._edit_and_delete(progress_message, error_text)
        except Exception as e:
            error_text = f"<b>Error:</b> An unexpected error occurred.\n<code>{html.escape(str(e))}</code>"
            await self._edit_and_delete(progress_message, error_text)

    async def _format_response(self, response: Message, user: User, start_time: datetime) -> str:
        """Memformat balasan dari bot menjadi lebih menarik."""
        rtt = fmtsec(start_time)
        header = f"<b>Name History for {user.mention}</b>\n<b>ID:</b> <code>{user.id}</code>\n\n"
        footer = f"<b><blockquote>{rtt}</blockquote></b>"

        if response.text:
            # Parsing riwayat nama dari teks
            history_lines = response.text.splitlines()
            # Lewati header asli dari bot
            name_entries = [line.strip() for line in history_lines if line.strip().startswith("•")]
            if name_entries:
                formatted_history = "\n".join(name_entries)
                return f"{header}<blockquote>{formatted_history}</blockquote>\n{footer}"
            else:
                # Jika tidak ada riwayat, tampilkan pesan dari bot
                # (misal: "This user has no name changes on record.")
                return f"{header}<blockquote>{html.escape(history_lines[-1])}</blockquote>\n{footer}"
        elif response.caption:
            # Jika bot membalas dengan media + caption
            return f"{header}<blockquote>{html.escape(response.caption)}</blockquote>\n{footer}"
        else:
            # Jika bot hanya membalas dengan media (misal: stiker "no history")
            return f"{header}<blockquote>Bot returned a non-text response.</blockquote>\n{footer}"

    async def _find_bot_response(
        self, client, start_time: datetime, timeout: int
    ) -> Message | None:
        """Mencari balasan dari bot dalam riwayat obrolan."""
        end_time = start_time + datetime.timedelta(seconds=timeout)
        while datetime.datetime.now(timezone.utc) < end_time:
            try:
                # Ambil pesan terakhir dari riwayat chat dengan bot
                async for last_message in client.get_chat_history(
                    SANGMATA_BOT_USERNAME, limit=1
                ):
                    # Pastikan pesan tersebut bukan dari kita dan dikirim setelah perintah kita
                    if (
                        last_message.date > start_time
                        and not last_message.from_user.is_self
                    ):
                        return last_message
            except Exception:
                # Abaikan error jika terjadi (misal, chat history kosong)
                pass
            await asyncio.sleep(1)  # Beri jeda sebelum memeriksa lagi
        return None

    async def _edit_and_delete(self, message: Message, text: str):
        """Mengedit pesan dan menghapusnya setelah durasi tertentu."""
        try:
            await message.edit_text(text, disable_web_page_preview=True)
            await asyncio.sleep(ERROR_VISIBLE_DURATION)
            await message.delete()
        except Exception:
            # Abaikan jika pesan sudah terhapus atau terjadi error lain
            pass
                if response.text:
                    await event.reply_text(
                        response.text.html + footer,
                        reply_to_message_id=event.reply_to_message_id or event.id,
                        disable_web_page_preview=True,
                    )
                else:
                    # Jika bukan teks (misal: foto), salin dan coba edit caption jika ada
                    await response.copy(event.chat.id, caption=(response.caption or "") + footer, reply_to_message_id=event.reply_to_message_id or event.id)
            else:
                raise asyncio.TimeoutError(f"@{SANGMATA_BOT_USERNAME} did not respond in time.")

        except UserIsBlocked:
            error_text = f"<b>Error:</b> Please unblock <a href='tg://resolve?domain={SANGMATA_BOT_USERNAME}'>@{SANGMATA_BOT_USERNAME}</a> and try again."
            await self._edit_and_delete(progress_message, error_text)
        except Exception as e:
            error_text = f"<b>Error:</b> An unexpected error occurred.\n<code>{html.escape(str(e))}</code>"
            await self._edit_and_delete(progress_message, error_text)

    async def _find_bot_response(
        self, client, start_time: datetime, timeout: int
    ) -> Message | None:
        """Mencari balasan dari bot dalam riwayat obrolan."""
        end_time = start_time + datetime.timedelta(seconds=timeout)
        while datetime.datetime.now(timezone.utc) < end_time:
            try:
                # Ambil pesan terakhir dari riwayat chat dengan bot
                async for last_message in client.get_chat_history(
                    SANGMATA_BOT_USERNAME, limit=1
                ):
                    # Pastikan pesan tersebut bukan dari kita dan dikirim setelah perintah kita
                    if (
                        last_message.date > start_time
                        and not last_message.from_user.is_self
                    ):
                        return last_message
            except Exception:
                # Abaikan error jika terjadi (misal, chat history kosong)
                pass
            await asyncio.sleep(1)  # Beri jeda sebelum memeriksa lagi
        return None

    async def _edit_and_delete(self, message: Message, text: str):
        """Mengedit pesan dan menghapusnya setelah durasi tertentu."""
        try:
            await message.edit_text(text, disable_web_page_preview=True)
            await asyncio.sleep(ERROR_VISIBLE_DURATION)
            await message.delete()
        except Exception:
            # Abaikan jika pesan sudah terhapus atau terjadi error lain
            pass
import asyncio
import datetime
import html
import re
from datetime import timezone

from pyrogram import filters
from pyrogram.errors import UserIsBlocked
from pyrogram.raw import functions
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

SPAM_BOT_USERNAME = "SpamBot"
SPAM_BOT_TIMEOUT = 20


class Stats(Module):
    """Module to display user account statistics."""

    name = "Stats"
    cmds = "stats"
    desc = "Shows your account statistics, including sent/received messages, sticker creations, and uptime."
    pattern = re.compile(r"^stats$")

    async def on_starting(self) -> None:
        """Initialize the start time when the module is loaded."""
        if not hasattr(self.client, "start_time"):
            self.client.start_time = datetime.datetime.now(timezone.utc)

    @listener.handler(filters.regex(pattern), priority=1)
    async def on_message_out(self, event: Message) -> None:
        """Handles the .stats command."""
        await event.edit_text("<code>Gathering stats...</code>")
        now = datetime.datetime.now(timezone.utc)

        try:
            # Jalankan semua pengumpulan data secara bersamaan
            spam_bot_stats, kang_count, uptime_str = await asyncio.gather(
                self._get_spambot_stats(event),
                self._get_kang_count(),
                self._get_uptime(),
            )

            stats_data = {
                "Pesan Terkirim": spam_bot_stats.get("sent", "N/A"),
                "Pesan Diterima": spam_bot_stats.get("received", "N/A"),
                "Stiker Terkirim": spam_bot_stats.get("stickers", "N/A"),
                "Stiker Dibuat (kang)": kang_count,
                "Waktu Aktif": uptime_str,
            }

            await event.edit_text(fmtstr("📊 User Stats", stats_data, fmtsec(now)))

        except UserIsBlocked:
            await event.edit_text(
                f"<b>Error:</b> Please unblock <a href='tg://resolve?domain={SPAM_BOT_USERNAME}'>@{SPAM_BOT_USERNAME}</a> and try again."
            )
        except Exception as e:
            await event.edit_text(f"<b>Error:</b>\n<code>{html.escape(str(e))}</code>")

    async def _get_spambot_stats(self, event: Message) -> dict:
        """Fetches message stats from @SpamBot."""
        start_time = datetime.datetime.now(timezone.utc)
        await event._client.send_message(SPAM_BOT_USERNAME, "/stats")

        response = await self._find_bot_response(event._client, start_time, SPAM_BOT_TIMEOUT)

        if not response or not response.text:
            raise asyncio.TimeoutError(f"@{SPAM_BOT_USERNAME} did not respond in time.")

        stats = {}
        # Pola regex untuk mengekstrak angka dari teks balasan
        patterns = {
            "sent": r"Messages sent: (\d+)",
            "received": r"Messages received: (\d+)",
            "stickers": r"Stickers sent: (\d+)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, response.text)
            stats[key] = match.group(1) if match else "N/A"

        return stats

    async def _find_bot_response(self, client, start_time: datetime, timeout: int) -> Message | None:
        """Finds a response from the bot in chat history."""
        end_time = start_time + datetime.timedelta(seconds=timeout)
        while datetime.datetime.now(timezone.utc) < end_time:
            async for last_message in client.get_chat_history(SPAM_BOT_USERNAME, limit=1):
                if last_message.date > start_time and not last_message.from_user.is_self:
                    return last_message
            await asyncio.sleep(1)
        return None

    async def _get_kang_count(self) -> int:
        """Counts the total number of stickers in user's 'kang' packs."""
        total_stickers = 0
        user_id = self.client.app.me.id
        try:
            sticker_sets = await self.client.app.invoke(functions.messages.GetAllStickers(hash=0))
            for stickerset in sticker_sets.sets:
                # Mencocokkan pola nama pack yang dibuat oleh modul sticker
                if stickerset.short_name.startswith(f"kang_{user_id}_"):
                    total_stickers += stickerset.count
        except Exception:
            # Jika gagal, kembalikan 0
            return 0
        return total_stickers

    async def _get_uptime(self) -> str:
        """Calculates the bot's uptime."""
        uptime_delta = datetime.datetime.now(timezone.utc) - self.client.start_time
        days = uptime_delta.days
        hours, rem = divmod(uptime_delta.seconds, 3600)
        minutes, seconds = divmod(rem, 60)

        parts = []
        if days > 0: parts.append(f"{days}d")
        if hours > 0: parts.append(f"{hours}h")
        if minutes > 0: parts.append(f"{minutes}m")
        if seconds > 0 or not parts: parts.append(f"{seconds}s")

        return " ".join(parts)
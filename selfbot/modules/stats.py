import asyncio
import datetime
import html
import re
from datetime import timezone

from pyrogram import filters
from pyrogram.raw import functions
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr
 
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
 
        # Membuat schema dan tabel jika belum ada
        await self.client.db.execute(
            """
            CREATE SCHEMA IF NOT EXISTS stats;
            CREATE TABLE IF NOT EXISTS stats.messages (
                type TEXT PRIMARY KEY,
                count BIGINT DEFAULT 0
            );
            """
        )
        # Memastikan baris untuk setiap tipe statistik ada
        await self.client.db.execute(
            """
            INSERT INTO stats.messages (type, count) VALUES ('sent', 0), ('received', 0), ('stickers_sent', 0)
            ON CONFLICT (type) DO NOTHING;
            """
        )
 
    @listener.handler(filters.regex(pattern), priority=1)
    async def on_message_out(self, event: Message) -> None:
        """Handles the .stats command."""
        await event.edit_text("<code>Gathering stats...</code>")
        now = datetime.datetime.now(timezone.utc)
 
        try:
            # Jalankan semua pengumpulan data secara bersamaan
            db_stats, kang_count, uptime_str = await asyncio.gather(
                self._get_db_stats(),
                self._get_kang_count(),
                self._get_uptime(),
            )
 
            stats_data = {
                "Pesan Terkirim": db_stats.get("sent", 0),
                "Pesan Diterima": db_stats.get("received", 0),
                "Stiker Terkirim": db_stats.get("stickers_sent", 0),
                "Stiker Dibuat (kang)": kang_count,
                "Waktu Aktif": uptime_str,
            }
 
            await event.edit_text(fmtstr("📊 User Stats", stats_data, fmtsec(now)))
 
        except Exception as e:
            await event.edit_text(f"<b>Error:</b>\n<code>{html.escape(str(e))}</code>")
 
    async def _get_db_stats(self) -> dict:
        """Mengambil statistik dari database."""
        rows = await self.client.db.fetch("SELECT type, count FROM stats.messages;")
        stats = {}
        for row in rows:
            stats[row["type"]] = row["count"]
        return stats
 
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
        except Exception: # nosec
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

    # --- Listeners untuk melacak statistik ---

    @listener.handler(filters.outgoing & ~filters.via_bot, priority=100)
    async def track_sent_messages(self, event: Message) -> None:
        """Melacak pesan terkirim."""
        await self.client.db.execute(
            "UPDATE stats.messages SET count = count + 1 WHERE type = 'sent';"
        )
        if event.sticker:
            await self.client.db.execute(
                "UPDATE stats.messages SET count = count + 1 WHERE type = 'stickers_sent';"
            )

    @listener.handler(filters.incoming & ~filters.via_bot, priority=100)
    async def track_received_messages(self, _: Message) -> None:
        """Melacak pesan diterima."""
        await self.client.db.execute(
            "UPDATE stats.messages SET count = count + 1 WHERE type = 'received';"
        )
import asyncio
import datetime
import re

import psutil
from pyrogram import filters
from pyrogram.enums import MessageMediaType
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(r"^stats$")
kang_pattern = re.compile(r"^kang(\s-f)?$")


class Stats(Module):
    name = "Stats"
    cmds = "stats"
    desc = "Displays usage statistics for your userbot."

    async def on_starting(self) -> None:
        """Initialize the module, create DB table, and set start time."""
        self.start_time = datetime.datetime.now(datetime.UTC)
        self.logger.info("Initializing stats table...")
        await self.client.db.execute(
            """
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value BIGINT NOT NULL DEFAULT 0
            );
            """
        )
        # Pastikan semua kunci statistik ada di database
        stats_keys = [
            "messages_sent",
            "messages_received",
            "stickers_sent",
            "stickers_kanged",
        ]
        for key in stats_keys:
            await self.client.db.execute(
                """
                INSERT INTO stats (key, value) VALUES ($1, 0)
                ON CONFLICT (key) DO NOTHING;
                """,
                key,
            )
        self.logger.info("Stats module initialized.")

    async def _increment_stat(self, key: str, amount: int = 1):
        """Helper function to increment a statistic in the database."""
        await self.client.db.execute(
            "UPDATE stats SET value = value + $1 WHERE key = $2", amount, key
        )

    @listener.handler(filters.outgoing, group=99, priority=3)
    async def on_outgoing_message(self, event: Message):
        """Catches all outgoing messages to increment stats."""
        if event.text and (
            event.text.startswith(".") or event.text.startswith("/")
        ):  # Abaikan command
            return

        await self._increment_stat("messages_sent")
        if event.media == MessageMediaType.STICKER:
            await self._increment_stat("stickers_sent")

    @listener.handler(filters.incoming, group=99, priority=3)
    async def on_incoming_message(self, _: Message):
        """Catches all incoming messages to increment stats."""
        await self._increment_stat("messages_received")

    @listener.handler(filters.regex(kang_pattern) & listener.fltrep, group=98, priority=3)
    async def on_kang_command(self, _: Message):
        """Catches the .kang command."""
        await self._increment_stat("stickers_kanged")

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, priority=1)
    async def on_stats_command(self, event: Message) -> None:
        """Handles the .stats command."""
        await event.edit_text("<code>Gathering stats...</code>")
        now = datetime.datetime.now(datetime.UTC)

        # Ambil semua statistik dari database
        rows = await self.client.db.fetch("SELECT key, value FROM stats;")
        stats_data = {row["key"]: row["value"] for row in rows}

        # Hitung uptime
        uptime = now - self.start_time
        uptime_str = str(uptime).split(".")[0]

        # Format output
        display_data = {
            "Messages Sent": stats_data.get("messages_sent", 0),
            "Messages Received": stats_data.get("messages_received", 0),
            "Stickers Sent": stats_data.get("stickers_sent", 0),
            "Stickers Kanged": stats_data.get("stickers_kanged", 0),
            "Uptime": uptime_str,
        }

        await event.edit_text(fmtstr("Userbot Stats", display_data, fmtsec(now)))


# Helper untuk memastikan modul ini dimuat ulang dengan benar saat restart
def __getattr__(name):
    if name == "Stats":
        return Stats
    raise AttributeError(f"module {__name__} has no attribute {name}")

def __dir__():
    return ["Stats"]
import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(r"^stats(?:\s+(reset))?$")


class Stats(Module):
    name = "Stats"
    cmds = "stats (reset)?"
    desc = {
        "Info": "Shows usage statistics of your userbot.",
        "reset": "Resets all collected statistics.",
        "?": "Optional",
        "e.g.": "stats",
    }

    async def on_starting(self) -> None:
        """Create the stats table if it doesn't exist."""
        await self.client.db.execute(
            """
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value BIGINT NOT NULL DEFAULT 0
            );
            """
        )
        # Initialize start time if it's a fresh start
        if not await self.get_stat("start_time_utc"):
            await self.set_stat(
                "start_time_utc", int(self.client.start_time_utc.timestamp())
            )

    # --- Database Helpers ---
    async def get_stat(self, key: str) -> int:
        """Gets a statistic value from the database."""
        return await self.client.db.fetchval(
            "SELECT value FROM stats WHERE key = $1", key
        )

    async def set_stat(self, key: str, value: int) -> None:
        """Sets or updates a statistic value."""
        await self.client.db.execute(
            """
            INSERT INTO stats (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = $2;
            """,
            key,
            value,
        )

    async def inc_stat(self, key: str, amount: int = 1) -> None:
        """Increments a statistic value."""
        await self.client.db.execute(
            """
            INSERT INTO stats (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = stats.value + $2;
            """,
            key,
            amount,
        )

    # --- Event Listeners for Stat Collection ---
    @listener.handler(filters.outgoing, 3)
    async def on_message_out_stat(self, msg: Message) -> None:
        """Log outgoing messages."""
        await self.inc_stat("sent")
        if msg.sticker:
            await self.inc_stat("sent_stickers")
        # Check if it's a command by checking if it matches any module's pattern
        if any(
            mod.name != self.name and hasattr(mod, "pattern") and getattr(mod, "pattern", None) and mod.pattern.match(msg.text or "")
            for mod in self.client.modules.values()
        ):
            await self.inc_stat("processed")

    @listener.handler(filters.incoming, 3)
    async def on_message_in_stat(self, msg: Message) -> None:
        """Log incoming messages."""
        await self.inc_stat("received")
        if msg.sticker:
            await self.inc_stat("received_stickers")

    # --- Command Handler ---
    @listener.handler(filters.regex(pattern) & ~listener.fltrep, priority=1)
    async def cmd_stats(self, event: Message) -> None:
        """Handles the .stats command."""
        now = datetime.datetime.now(datetime.UTC)
        match = pattern.match(event.text)
        reset_arg = match.group(1)

        if reset_arg == "reset":
            await event.edit_text("<code>Resetting stats...</code>")
            await self.client.db.execute("TRUNCATE TABLE stats;")
            await self.set_stat(
                "start_time_utc", int(self.client.start_time_utc.timestamp())
            )
            await event.edit_text("✅ <b>Stats have been reset.</b>")
            return

        await event.edit_text("<code>Calculating stats...</code>")

        start_timestamp = await self.get_stat("start_time_utc")
        start_time = datetime.datetime.fromtimestamp(
            start_timestamp, tz=datetime.UTC
        )
        uptime_delta = now - start_time

        sent = await self.get_stat("sent") or 0
        sent_stickers = await self.get_stat("sent_stickers") or 0
        received = await self.get_stat("received") or 0
        received_stickers = await self.get_stat("received_stickers") or 0
        processed = await self.get_stat("processed") or 0

        # Helper functions for calculations
        def _calc_pct(num1: int, num2: int) -> str:
            return f"{(num1 / num2) * 100:.1f}" if num2 else "0"

        def _calc_ph(stat: int) -> str:
            up_hr = max(1, uptime_delta.total_seconds()) / 3600
            return f"{stat / up_hr:.1f}"

        # Formatting the output
        stats_data = {
            "Uptime": str(uptime_delta).split(".")[0],
            "Msgs Received": f"{received} ({_calc_ph(received)}/h) • {_calc_pct(received_stickers, received)}% stickers",
            "Msgs Sent": f"{sent} ({_calc_ph(sent)}/h) • {_calc_pct(sent_stickers, sent)}% stickers",
            "Commands Processed": f"{processed} ({_calc_ph(processed)}/h) • {_calc_pct(processed, sent)}% of sent",
        }

        await event.edit_text(fmtstr("Userbot Stats", stats_data, fmtsec(now)))
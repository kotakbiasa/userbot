import asyncio
import datetime
import html
import re

import speedtest
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(r"^speed(?:test)?$")


class Speedtest(Module):
    name = "Speedtest"

    cmds = "speed(test)?"
    desc = {
        "?": "Optional",
        "e.g.": "speedtest",
        "Info": "Runs an internet speed test and displays the results.",
    }

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, priority=1)
    async def on_message_out(self, event: Message) -> None:
        """Runs an internet speed test."""
        await event.edit_text("<code>Running speedtest...</code>")
        now = datetime.datetime.now(datetime.UTC)

        try:
            # Run the synchronous speedtest function in a separate thread
            results = await asyncio.to_thread(self.run_speed_test)

            # Format the results
            output = fmtstr(
                "Speedtest Results",
                {
                    "Provider": results['client']['isp'],
                    "Server": f"{results['server']['name']} ({results['server']['country']})",
                    "Ping": f"{results['ping']:.2f} ms",
                    "Download": f"{results['download'] / 1_000_000:.2f} Mbps",
                    "Upload": f"{results['upload'] / 1_000_000:.2f} Mbps",
                },
                fmtsec(now),
            )
            await event.edit_text(output)

        except Exception as e:
            await event.edit_text(
                f"<b>Speedtest failed:</b>\n<code>{html.escape(str(e))}</code>"
            )

    def run_speed_test(self) -> dict:
        """Synchronous function to run the speedtest."""
        s = speedtest.Speedtest(secure=True)
        s.get_best_server()
        s.download()
        s.upload()
        return s.results.dict()
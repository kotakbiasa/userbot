import datetime
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

pattern = re.compile(r"^ping$")


class Ping(Module):
    name = "Ping"
    cmds = "ping"
    desc = {
        "Info": "Checks the bot's response time.",
        "e.g.": "ping",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Calculates and shows the bot's ping."""
        start = datetime.datetime.now(datetime.UTC)
        await event.edit_text("<code>Pong!</code>")
        end = datetime.datetime.now(datetime.UTC)
        ping_time = (end - start).microseconds / 1000
        await event.edit_text(f"<b>Pong!</b>\n<code>{ping_time:.3f} ms</code>")
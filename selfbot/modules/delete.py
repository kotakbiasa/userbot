import asyncio
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

pattern = re.compile(r"^d(?:el(?:ete)?)?$")


class Delete(Module):
    name = "Delete Message"
    cmds = "<Reply> d(el(ete)?)?"
    desc = {"?": "Optional", "e.g.": "<Reply> del"}

    @listener.handler(filters.regex(pattern) & listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        await asyncio.gather(event.delete(), event.reply_to_message.delete())

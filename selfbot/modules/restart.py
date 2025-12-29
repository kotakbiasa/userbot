import asyncio
import os
import re
import sys

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

pattern = re.compile(r"^r(?:estart)?$")


class Restart(Module):
    name = "Restart System"
    cmds = "r(estart)?"
    desc = {"?": "Optional", "e.g": "restart"}

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        await asyncio.gather(
            event.edit_text("<code>Restarting...</code>"),
            self.client.db.execute(
                "INSERT INTO restart.msg (chat_id, message_id) VALUES ($1, $2);",
                event.chat.id,
                event.id,
            ),
        )
        os.execv(sys.argv[0], sys.argv)

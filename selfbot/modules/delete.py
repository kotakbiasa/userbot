import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

pattern = re.compile(r"^d(?:el(?:ete)?)?$")


class Delete(Module):
    name = "Delete"
    cmds = "<Reply to Message>? d(el(ete)?)?"
    desc = {"?": "Optional", "e.g.": "delete"}

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        ids = [event.id]
        if event.reply_to_message_id:
            ids.append(event.reply_to_message_id)

        await event._client.delete_messages(event.chat.id, ids)

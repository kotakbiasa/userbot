import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

pattern = re.compile(r"^(?:/)?d(?:el)?(?:_(\d{1,10}))?$")


class Delete(Module):
    name = "Delete"

    cmds = "<Reply to Message>? /?d(el)?(_{id})?"
    desc = {"id": "Message ID", "?": "Optional", "e.g.": "/del_123"}

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        ids, (mid,) = [event.id], pattern.match(event.content).groups()
        if mid:
            ids.append(int(mid))

        if event.reply_to_message_id:
            ids.append(event.reply_to_message_id)

        await event._client.delete_messages(event.chat.id, ids)

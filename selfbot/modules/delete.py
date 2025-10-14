import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

pattern = re.compile(r"^(?:/)?d(?:el)?(?:_(\d{1,10}))$")


class Delete(Module):
    name = "Delete"

    cmds = "<Reply to Message>? /?d(el)?(_{id})?"
    desc = {"id": "Message ID", "?": "Optional", "e.g.": "/del_123"}

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        (mid,) = pattern.match(event.content).groups()
        if event.reply_to_message_id:
            mid = event.reply_to_message_id

        await event.delete(True)

        if mid:
            try:
                msg = await event._client.get_messages(event.chat.id, int(mid))
            except RPCError:
                pass
            else:
                ids = [msg.id]
                if (
                    msg.reply_to_message_id
                    and msg.reply_to_message.from_user
                    and msg.reply_to_message.from_user.is_self
                ):
                    ids.append(msg.reply_to_message_id)

                await event._client.delete_messages(event.chat.id, ids)

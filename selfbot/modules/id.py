import datetime
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(r"^id$")


class Id(Module):
    name = "ID"
    cmds = "id"
    desc = {
        "Info": "Get the ID of the current chat, replied user/message, or sticker.",
        "e.g.": "<Reply> id",
    }

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        """Fetches and displays various IDs based on context."""
        now = datetime.datetime.now(datetime.UTC)
        data = {"Chat ID": event.chat.id}

        replied = event.reply_to_message
        if replied:
            data["Replied Msg ID"] = replied.id
            if replied.from_user:
                data["User ID"] = replied.from_user.id
            if replied.forward_from:
                data["Fwd User ID"] = replied.forward_from.id
            if replied.sticker:
                data["Sticker ID"] = replied.sticker.file_id
                data["Sticker Pack"] = replied.sticker.set_name
        else:
            data["Your ID"] = event.from_user.id

        output = fmtstr("IDs", data, fmtsec(now))

        await event.edit_text(output, disable_web_page_preview=True)
import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(r"^purge(me)?(\s(\d{1,3}))?$")


class Purge(Module):
    name = "Purge"

    cmds = "<Reply to Message>? purge(me)? [1-999]?"
    desc = {
        "Reply to Message": "as Start ID (Default: 1)",
        "?": "Optional",
        "e.g.": "purgeme 99",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")
        match, limit = pattern.match(event.content), 0
        if match.group(2):
            limit = int(match.group(3))

        ids = []
        if match.group(1):
            ids = [
                m.id
                async for m in event._client.search_messages(
                    event.chat.id,
                    from_user="me",
                    min_id=event.reply_to_message_id or 1,
                    max_id=event.id,
                    limit=(limit or 100) + 1,
                )
            ]
        else:
            if event.chat.type not in [ChatType.SUPERGROUP, ChatType.CHANNEL]:
                return
            elif event.reply_to_message_id:
                if limit:
                    ids = range(
                        event.reply_to_message_id, event.reply_to_message_id + limit
                    )
                else:
                    ids = range(event.reply_to_message_id, event.id)
            else:
                end = limit or 100
                ids = range(event.id - 1, event.id - (end + 1), -1)

        res, now = 0, datetime.datetime.now()
        for chunk in [ids[i : i + 100] for i in range(0, len(ids), 100)]:
            res += await self.client.app.delete_messages(event.chat.id, chunk)
            if res % 100 == 0:
                await asyncio.sleep(2.5)

        await event.edit_text(
            fmtstr("Purge", f"{res} Message{'' if res == 1 else 's'}", fmtsec(now))
        )

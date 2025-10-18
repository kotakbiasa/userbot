import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(r"^purge(me)?(?:\s(\d{1,3}))?(?:\s(-d))?$")


class Purge(Module):
    name = "Purge"
    cmds = "<Reply to Message>? purge(me)? {limit}? (-d)?"
    desc = {
        "Reply to Message": "as Start ID (Default: 1)",
        "limit": "[1-999] (Default: 100)",
        "-d": "Delete Current Message",
        "?": "Optional",
        "e.g.": "purgeme 99",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")
        (me, digit, delete), limit = pattern.match(event.content).groups(), 0
        if digit:
            limit = int(digit)

        ids = []
        if me:
            ids = [
                m.id
                async for m in event._client.search_messages(
                    event.chat.id,
                    from_user="me",
                    min_id=(event.reply_to_message_id or 1) - 1,
                    max_id=event.id,
                    limit=(limit or 100) + 1,
                )
            ]
        else:
            if event.chat.type not in [ChatType.SUPERGROUP, ChatType.CHANNEL]:
                return await event.edit_text(
                    f"<code>Unsupported {html.escape(f'<{event.chat.type}>')}</code>"
                )
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

        res, now = 0, datetime.datetime.now(datetime.UTC)
        for chunk in [ids[i : i + 100] for i in range(0, len(ids), 100)]:
            res += await self.client.app.delete_messages(event.chat.id, chunk)
            if res % 100 == 0:
                await asyncio.sleep(2.5)

        if delete:
            return await event.delete()

        await event.edit_text(
            fmtstr(
                f"Purge{'me' if me else ''}",
                f"{res} Message{'' if res == 1 else 's'}",
                fmtsec(now),
            )
        )

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

pattern = re.compile(r"^purge(me)?(?:\s-l\s([1-9]\d{0,2}))?$")


class Purge(Module):
    name = "Purge Message"
    cmds = "<Reply>? purge(me)? (-l {limit})?"
    desc = {
        "Reply": "Min ID",
        "limit": "[1-999]",
        "?": "Optional",
        "e.g.": "purgeme -l 99",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")
        (me, limit) = pattern.match(event.content).groups()
        if limit:
            limit = int(limit)
        else:
            limit = 0

        mids = []
        if me:
            mids = [
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
            if event.chat.type not in (ChatType.SUPERGROUP, ChatType.CHANNEL) or (
                event.chat.type == ChatType.SUPERGROUP
                and (event.chat.is_direct_messages or event.chat.is_forum)
            ):
                await event.edit_text(
                    f"<code>Unsupported {html.escape('<ChatType>')}</code>"
                )
                return

            if event.reply_to_message_id:
                if limit:
                    mids = range(
                        event.reply_to_message_id, event.reply_to_message_id + limit
                    )
                else:
                    mids = range(event.reply_to_message_id, event.id)
            else:
                mids = range(event.id - 1, event.id - ((limit or 100) + 1), -1)

        res, now = 0, datetime.datetime.now(datetime.UTC)
        for chunk in (mids[i : i + 100] for i in range(0, len(mids), 100)):
            res += await event._client.delete_messages(event.chat.id, chunk)
            if res % 100 == 0:
                await asyncio.sleep(2.5)

        await asyncio.gather(
            event.edit_text(
                fmtstr(
                    f"Purge{'me' if me else ''}",
                    f"{res} Message{'' if res == 1 else 's'}",
                    fmtsec(now),
                )
            ),
            asyncio.sleep(2.5),
        )
        await event.delete()
import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.types import InlineQuery, Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtmsg, fmtsec, ikm

pattern = re.compile(r"^pmbl(?:\s-(msg|url)\s(.+))?$")


class PMBL(Module):
    name = "PM Block"
    cmds = "pmbl (-{key} {value})?"
    desc = {
        "pmbl": "Toggle",
        "key": "(msg|url)",
        "value": "String",
        "?": "Optional",
        "e.g.": "pmbl -msg Hello, World!",
    }
    status, msg, url = False, "Sorry, No PMs!", "t.me/resolveUsername"

    async def on_loading(self) -> None:
        row = await self.client.db.fetchrow("SELECT status, msg, url FROM pmbl.meta;")
        if not row:
            await self.client.db.execute(
                "INSERT INTO pmbl.meta (status, msg, url) VALUES ($1, $2, $3);",
                self.status,
                self.msg,
                self.url,
            )
            return

        self.status, self.msg, self.url = row["status"], row["msg"], row["url"]

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        now, (key, value) = (
            datetime.datetime.now(datetime.UTC),
            pattern.match(event.content).groups(),
        )
        if not key:
            self.status = not self.status
            key, value = "status", self.status
        else:
            if key == "msg":
                self.msg = value
            else:
                self.url = value

        await asyncio.gather(
            self.client.db.execute(f"UPDATE pmbl.meta SET {key} = $1;", value),
            event.edit_text(
                fmtmsg(
                    "PM Block",
                    {
                        "Status": self.status,
                        "Message": self.msg,
                        "Button URL": self.url,
                    },
                    fmtsec(now),
                )
            ),
        )

    @listener.handler(filters.private & ~listener.fltusr, 2)
    async def on_message_in(self, event: Message) -> None:
        _, res = await asyncio.gather(
            event._client.read_chat_history(event.chat.id, event.id),
            event._client.get_inline_bot_results(self.client.bot.me.id, "pmbl"),
        )
        await event.reply_inline_bot_result(res.query_id, res.results[0].id)
        if self.status:
            await asyncio.gather(event.from_user.archive(), event.from_user.block())

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await self.answer(
            event,
            ikm(("Feedback", "url", self.url)),
            f"<blockquote><b>{self.msg}</b></blockquote>",
        )

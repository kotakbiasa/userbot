import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import RPCError
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ids, ikm

QUERY = """
CREATE TABLE IF NOT EXISTS pmblock (
    active      BOOLEAN PRIMARY KEY DEFAULT FALSE,
    message     TEXT,
    feedback    TEXT
);
CREATE TABLE IF NOT EXISTS pmblock_auths (
    user_id BIGINT  PRIMARY KEY,
    auth    BOOLEAN DEFAULT FALSE
);
"""

pattern = re.compile(
    r"^"
    r"(?P<action>(?:#)?pmbl|auth)"
    r"(?:\s(?P<user>@?[a-zA-Z][a-zA-Z0-9_]{4,32}|\d{5,10})$)?"
    r"(?:\s(?P<set>msg|url)\s(?P<content>.+))?"
    r"$",
    re.DOTALL,
)


class PmBlock(Module):
    name = "PMBL"
    cmds = "(pmbl) *{set content} | (auth) *{user}"
    desc = {
        "*": "Optional",
        "set": "[msg, url]",
        "content": "String",
        "user": "[user_id, username, reply_user]",
    }

    async def on_starting(self) -> None:
        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

        await self.client.db.execute(QUERY)

        data = await self.client.db.fetch("SELECT * FROM pmblock;")
        if not data:
            self.pmbl = False
            self.text = "<b>Sorry, No PMs!</b>"
            self.link = "t.me/resolveUsername?direct"
            await self.client.db.execute(
                """
                INSERT INTO pmblock (active, message, feedback)
                VALUES ($1, $2, $3);
                """,
                self.pmbl,
                self.text,
                self.link,
            )
        else:
            self.pmbl = data[0]["active"]
            self.text = data[0]["message"]
            self.link = data[0]["feedback"]

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        data = pattern.match(event.content).groupdict()
        if data["action"] == "auth":
            if data["user"]:
                try:
                    user = await event._client.get_users(data["user"])
                except RPCError as e:
                    return await event.edit(f"<code>{e.__class__.__name__}</code>")
                else:
                    data["user"] = user.id
            else:
                if (
                    event.reply_to_message
                    and event.reply_to_message.from_user
                    and not event.reply_to_message.from_user.is_bot
                ):
                    data["user"] = event.reply_to_message.from_user.id
                elif event.chat.type == ChatType.PRIVATE:
                    data["user"] = event.chat.id
                else:
                    return await event.edit("<code>Reply to User or Give an ID</code>")

        async with self.lock:
            await self.data.put(data)

        res = await event._client.get_inline_bot_results(
            self.client.bot.me.id, event.content
        )
        await asyncio.gather(
            event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
                reply_parameters=ReplyParameters(
                    message_id=event.reply_to_message_id or event.id
                ),
            ),
            event.delete(True),
        )

    @listener.handler(filters.private, 2)
    async def on_message_in(self, event: Message) -> None:
        auth = await self.client.db.fetchval(
            """
            SELECT auth FROM pmblock_auths
            WHERE user_id = $1;
            """,
            event.from_user.id,
        )
        if auth:
            return

        res = await event._client.get_inline_bot_results(
            self.client.bot.me.id, f"#pmbl {event.from_user.id}"
        )
        await event.reply_inline_bot_result(
            res.query_id,
            res.results[0].id,
            reply_parameters=ReplyParameters(message_id=event.id),
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent("<code>...</code>"),
                )
            ],
            cache_time=900,
        )

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        if event.query.startswith("#"):
            await event.edit_message_text(
                self.text, reply_markup=ikm(("Feedback", "url", self.link))
            )
            return await self.client.app.block_user(int(event.query.split()[1]))

        if self.data.empty():
            return await self.client.app.delete_messages(
                *ids(event.inline_message_id), True
            )

        async with self.lock:
            data = await self.data.get()

        now = datetime.datetime.now()
        if data["action"] == "pmbl":
            if data["set"]:
                if data["set"] == "msg":
                    self.text = data["content"]
                    await self.client.db.execute(
                        "UPDATE pmblock SET message = $1", self.text
                    )
                else:
                    self.link = data["content"]
                    await self.client.db.execute(
                        "UPDATE pmblock SET Feedback = $1", self.link
                    )
            else:
                self.pmbl = not self.pmbl
                await self.client.db.execute(
                    "UPDATE pmblock SET active = $1", self.pmbl
                )

            return await event.edit_message_text(
                fmtstr(
                    "PM Auto Block",
                    {"Active": self.pmbl, "Feedback": self.link, "Message": self.text},
                    fmtsec(now),
                ),
                reply_markup=ikm(("Close", "0")),
            )

        auth = await self.client.db.fetchval(
            "SELECT auth FROM pmblock_auths WHERE user_id = $1;", data["user"]
        )
        await self.client.db.execute(
            """
            INSERT INTO pmblock_auths (user_id, auth)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET
                auth = EXCLUDED.auth
            """,
            data["user"],
            not auth,
        )
        await event.edit_message_text(
            fmtstr(
                "PM Auto Block",
                {"User ID": data["user"], "Authorized": not auth},
                fmtsec(now),
            ),
            reply_markup=ikm(("Close", "0")),
        )

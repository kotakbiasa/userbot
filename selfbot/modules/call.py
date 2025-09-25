import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)

load = True
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.pytgcalls_session import PyTgCallsSession
    from pytgcalls.types import GroupCallConfig
except Exception:
    load = False
else:
    PyTgCallsSession.notice_displayed = True

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ids, ikm

QUERY = """
CREATE TABLE IF NOT EXISTS call (
    chat_id BIGINT  PRIMARY KEY,
    joined  BOOLEAN DEFAULT FALSE,
    join_as BIGINT
);
"""

pattern = re.compile(
    r"^"
    r"(?P<action>(?:start|end|join|leave))call"
    r"(?:\s+(?P<chat>@?[a-zA-Z][a-zA-Z0-9_]{3,32}|-100\d{10}))?"
    r"(?:\s+as@(?P<as>@?[a-z][a-zA-Z0-9_]{3,32}|-100\d{10}))?"
    r"(?:\s+-t\s(?P<title>.+))?"
    r"$"
)


class Call(Module):
    name = "Call"
    cmds = "{action(call)} *{chat} *{(as@)peer} *{(-t) title}"
    desc = {
        "action": "[join, leave, start, end]",
        "*": "Optional",
        "chat": "[username, chat_id]",
        "peer": "[username, chat_id]",
        "title": "String",
    }

    async def on_starting(self) -> None:
        if not load:
            return self.client.unload(self)

        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

        self.client.tgc = PyTgCalls(self.client.app, 1, 900)
        await self.client.tgc.start()

        for group in list(self.client.app.dispatcher.groups.keys()):
            if group == -1:
                continue

            for handler in self.client.app.dispatcher.groups[group]:
                await asyncio.to_thread(self.client.app.remove_handler, handler, group)

            self.client.app.dispatcher.groups.pop(group, None)

        await self.client.db.execute(QUERY)
        rows = await self.client.db.fetch(
            "SELECT chat_id, join_as FROM call WHERE joined = TRUE"
        )
        for row in rows:
            args = {"chat_id": row["chat_id"]}
            if row.get("join_as"):
                try:
                    peer = await self.client.app.resolve_peer(row["join_as"])
                except RPCError:
                    pass
                else:
                    args["config"] = GroupCallConfig(join_as=peer)

            try:
                await self.client.tgc.play(**args)
            except Exception:
                await self.client.db.execute(
                    "UPDATE call SET joined = FALSE WHERE chat_id = $1;", row["chat_id"]
                )

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        data = pattern.match(event.content).groupdict()

        data["chat_id"] = event.chat.id
        if data["chat"]:
            try:
                chat = await self.client.app.get_chat(data["chat"], False)
            except RPCError as e:
                return await event.edit(f"<code>{e.__class__.__name__}</code>")
            else:
                data["chat_id"] = chat.id
            finally:
                data.pop("chat")

        if data["as"]:
            try:
                chat = await self.client.app.get_chat(data["as"], False)
            except RPCError as e:
                return await event.edit(f"<code>{e.__class__.__name__}</code>")
            else:
                data["as"] = chat.id

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

    @listener.handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent(
                        f"<code>{pattern.match(event.query).groupdict()['action'].title()} Call...</code>"
                    ),
                )
            ],
            cache_time=900,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        if self.data.empty():
            return await self.client.app.delete_messages(
                *ids(event.inline_message_id), True
            )

        async with self.lock:
            data = await self.data.get()

        text = {"data": {"Chat": data["chat_id"]}}

        func = None
        args = {"chat_id": data["chat_id"]}

        now = datetime.datetime.now()
        if data["action"] == "join":
            text["head"] = "Joined Call"
            if not data["as"]:
                text["data"]["Peer"] = "Self"
            else:
                try:
                    peer = await self.client.app.resolve_peer(data["as"])
                except RPCError as e:
                    return await event.edit_message_text(
                        f"<code>{e.__class__.__name__}</code>\n\n<b>{fmtsec(now)}</b>",
                        reply_markup=ikm(("Close", b"0")),
                    )
                else:
                    text["data"]["Peer"] = data["as"]
                    args["config"] = GroupCallConfig(join_as=peer)

            func = self.client.tgc.play

        elif data["action"] == "leave":
            text["head"] = "Left Call"
            func = self.client.tgc.leave_call

        elif data["action"] == "start":
            text["head"] = "Started Call"
            text["data"]["Title"] = "N/A"
            if data["title"]:
                text["data"]["Title"] = data["title"]
                args["title"] = data["title"]

            func = self.client.app.create_video_chat

        else:
            text["head"] = "Ended Call"
            func = self.client.app.discard_group_call

        try:
            await func(**args)
        except Exception as e:
            await event.edit_message_text(
                f"<code>{e.__class__.__name__}</code>\n\n<b>{fmtsec(now)}</b>",
                reply_markup=ikm(("Close", b"0")),
            )
        else:
            if data["action"] in ["join", "leave"]:
                await self.client.db.execute(
                    """
                    INSERT INTO call (chat_id, joined, join_as)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (chat_id) DO UPDATE SET
                        joined = EXCLUDED.joined,
                        join_as = EXCLUDED.join_as;
                    """,
                    data["chat_id"],
                    True if data["action"] == "join" else False,
                    data["as"],
                )

            await event.edit_message_text(
                fmtstr(**text, foot=fmtsec(now)), reply_markup=ikm(("Close", b"0"))
            )

import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.types import Message
from pyrogram.utils import get_channel_id

load: bool
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.pytgcalls_session import PyTgCallsSession
    from pytgcalls.types import GroupCallConfig
except Exception:
    load = False
else:
    load = True
    PyTgCallsSession.notice_displayed = True

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

schema = """
CREATE SCHEMA IF NOT EXISTS call;
CREATE TABLE IF NOT EXISTS call.chats (
    chat_id BIGINT  PRIMARY KEY,
    join_as BIGINT,
    mute    BOOLEAN DEFAULT FALSE
);
"""
pattern = re.compile(
    r"^"
    r"(?P<action>(?:start|end|join|leave)?)call"
    r"(?:\s+(?P<chat_id>@?[a-zA-Z][a-zA-Z0-9_]{3,32}|-100\d{10}))?"
    r"(?:\s+-as\s(?P<join_as>@?[a-zA-Z][a-zA-Z0-9_]{3,32}|-100\d{10}))?"
    r"(?:\s+(?P<mute>-m))?"
    r"(?:\s+-t\s(?P<title>.+))?"
    r"$"
)


class Call(Module):
    name = "Call"
    cmds = "{action}?call {chat}? (-as {peer})? (-m)? (-t {title})?"
    desc = {
        "action": "(join|leave|start|end)",
        "call": "Joined Call IDs (Standalone)",
        "chat": "Chat ID or Username (Default: Current Chat)",
        "peer": "Chat ID or Username (Default: Self)",
        "-m": "Mute",
        "title": "String",
        "?": "Optional",
        "e.g.": "startcall @durov -t Untitled",
    }

    async def on_starting(self) -> None:
        if not load:
            return self.client.unload(self)

        self.client.tgc = PyTgCalls(self.client.app, 1, 15)
        await self.client.tgc.start()
        for group in list(self.client.app.dispatcher.groups.keys()):
            if group == -1:
                continue

            for handler in self.client.app.dispatcher.groups[group]:
                await asyncio.to_thread(self.client.app.remove_handler, handler, group)

            self.client.app.dispatcher.groups.pop(group, None)

        await self.client.db.execute(schema)
        rows = await self.client.db.fetch(
            "SELECT chat_id, join_as, mute FROM call.chats;"
        )
        for row in rows:
            args = {"chat_id": row["chat_id"]}
            if row.get("join_as"):
                try:
                    peer = await self.client.app.resolve_peer(row["join_as"])
                except RPCError:
                    await self.client.db.execute(
                        "UPDATE call.chats SET join_as = NULL WHERE chat_id = $1;",
                        row["chat_id"],
                    )
                else:
                    args["config"] = GroupCallConfig(join_as=peer)

            try:
                await self.client.tgc.play(**args)
            except Exception:
                continue
            else:
                if row.get("mute"):
                    await self.client.tgc.mute(row["chat_id"])

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")
        now, (action, chat_id, join_as, mute, title) = (
            datetime.datetime.now(datetime.UTC),
            pattern.match(event.content).groupdict().values(),
        )
        if not action:
            return await event.edit_text(
                fmtstr(
                    "Joined Call IDs", list(await self.client.tgc.calls), fmtsec(now)
                )
            )

        if not chat_id:
            chat_id = event.chat.id
        else:
            try:
                chat = await event._client.get_chat(chat_id, False)
            except RPCError as e:
                return await event.edit_text(
                    fmtstr(
                        e.__class__.__name__,
                        e.MESSAGE.format(value=e.value),
                        fmtsec(now),
                    )
                )
            else:
                chat_id = chat.id

        func = None
        args = {"chat_id": chat_id}
        text = {"data": {"Chat ID": chat_id}}
        if action == "join":
            func = self.client.tgc.play
            text["head"] = "Joined Call"
            if join_as:
                try:
                    peer = await event._client.resolve_peer(join_as)
                except RPCError as e:
                    return await event.edit_text(
                        fmtstr(
                            e.__class__.__name__,
                            e.MESSAGE.format(value=e.value),
                            fmtsec(now),
                        )
                    )
                else:
                    join_as = get_channel_id(peer.channel_id)
                    text["data"]["Join as"] = join_as
                    args["config"] = GroupCallConfig(join_as=peer)

            text["data"]["Mute"] = bool(mute)
        elif action == "leave":
            func = self.client.tgc.leave_call
            text["head"] = "Left Call"
        elif action == "start":
            func = event._client.create_video_chat
            text["head"] = "Started Call"
            if title:
                args["title"] = title
                text["data"]["Title"] = title
        else:
            func = event._client.discard_group_call
            text["head"] = "Ended Call"

        try:
            await func(**args)
        except RPCError as e:
            await event.edit_text(
                fmtstr(
                    e.__class__.__name__, e.MESSAGE.format(value=e.value), fmtsec(now)
                )
            )
        else:
            if action == "join":
                if mute:
                    await self.client.tgc.mute(chat_id)
                else:
                    await self.client.tgc.unmute(chat_id)

                await self.client.db.execute(
                    """
                    INSERT INTO call.chats AS c (chat_id, join_as, mute)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (chat_id)
                    DO UPDATE SET
                        join_as = EXCLUDED.join_as,
                        mute = EXCLUDED.mute
                    WHERE c.join_as IS DISTINCT FROM EXCLUDED.join_as
                       OR c.mute    IS DISTINCT FROM EXCLUDED.mute;
                    """,
                    chat_id,
                    join_as,
                    bool(mute),
                )
            elif action == "leave":
                await self.client.db.execute(
                    "DELETE FROM call.chats WHERE chat_id = $1;", chat_id
                )

            await event.edit_text(fmtstr(**text, foot=fmtsec(now)))

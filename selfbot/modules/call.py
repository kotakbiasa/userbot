import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import ChannelPrivate, PeerIdInvalid, RPCError
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

pattern = re.compile(
    r"^"
    r"(?P<action>(?:start|end|join|leave)?)call"
    r"(?:\s+(?P<chat_id>@?[a-zA-Z][a-zA-Z0-9_]{3,31}|-100[1-9]\d{9}))?"
    r"(?:\s+-as\s(?P<join_as>@?[a-zA-Z][a-zA-Z0-9_][a-zA-Z0-9]{2,30}))?"
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
        "peer": "Username (Default: Self)",
        "-m": "Mute",
        "title": "String",
        "?": "Optional",
        "e.g.": "startcall @durov -t Title",
    }

    async def on_starting(self) -> None:
        if not load:
            self.logger.warning("PyTgCalls None")
            self.client.unload(self)
            return

        self.client.call = PyTgCalls(self.client.app, 1, 15)
        self.logger.info("Starting PyTgCalls...")
        try:
            await self.client.call.start()
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
        else:
            self.logger.info("PyTgCalls Started")
            for group in list(self.client.app.dispatcher.groups.keys()):
                if group == -1:
                    continue

                for handler in self.client.app.dispatcher.groups[group]:
                    await asyncio.to_thread(
                        self.client.app.remove_handler, handler, group
                    )

                self.client.app.dispatcher.groups.pop(group, None)

    async def on_started(self) -> None:
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
                await self.client.call.play(**args)
            except Exception as e:
                if isinstance(e, (ChannelPrivate, PeerIdInvalid)):
                    await self.client.db.execute(
                        "DELETE FROM call.chats WHERE chat_id = $1;", row["chat_id"]
                    )
                else:
                    continue
            else:
                if row.get("mute"):
                    await self.client.call.mute(row["chat_id"])

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")

        now, (action, chat_id, join_as, mute, title) = (
            datetime.datetime.now(datetime.UTC),
            pattern.match(event.content).groupdict().values(),
        )
        if not action:
            return await event.edit_text(
                fmtstr(
                    "Joined Call IDs", list(await self.client.call.calls), fmtsec(now)
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

        func, args, text = None, {"chat_id": chat_id}, {"data": {"Chat ID": chat_id}}
        if action == "join":
            func = self.client.call.play
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
            func = self.client.call.leave_call
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
                    await self.client.call.mute(chat_id)
                else:
                    await self.client.call.unmute(chat_id)

                await self.client.db.execute(
                    """
                    INSERT INTO call.chats AS c (
                        chat_id,
                        join_as,
                        mute
                    )
                    VALUES ($1, $2, $3)
                    ON CONFLICT (chat_id)
                    DO UPDATE SET
                        join_as = EXCLUDED.join_as,
                        mute    = EXCLUDED.mute
                    WHERE
                        c.join_as IS DISTINCT FROM EXCLUDED.join_as
                    OR  c.mute    IS DISTINCT FROM EXCLUDED.mute;
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

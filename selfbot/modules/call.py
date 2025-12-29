import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import ChannelPrivate, PeerIdInvalid, RPCError
from pyrogram.types import Message
from pyrogram.utils import get_channel_id

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtmsg, fmtsec

load = True
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.pytgcalls_session import PyTgCallsSession
    from pytgcalls.types import GroupCallConfig
except Exception:
    load = False
else:
    PyTgCallsSession.notice_displayed = True

pattern = re.compile(
    r"^call(?:\s-(start|end|join|leave))"
    r"(?:\s(@?[a-zA-Z][a-zA-Z0-9_]{2,31}[a-zA-Z0-9]|-100[1-9]\d{9}|[1-9]\d{1,9}))?"
    r"(?:\s-as\s(@?[a-zA-Z][a-zA-Z0-9_]{1,31}[a-zA-Z0-9]))?"
    r"(?:\s(-mute))?(?:\s-t\s(.+))?$"
)


class Call(Module):
    name = "Group Call"
    cmds = "call -{action} {chat}? (-as {peer})? (-mute)? (-t {title})?"
    desc = {
        "action": "(join|leave|start|end)",
        "chat": "Chat ID or Username",
        "peer": "Username",
        "title": "String",
        "?": "Optional",
        "e.g.": "call -join @durov -mute",
    }

    async def on_loading(self) -> None:
        if not load:
            self.client.unload(self)
            return

        self.client.call = PyTgCalls(self.client.app, 1, 15)
        try:
            await self.client.call.start()
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            self.client.unload(self)
        else:
            for group in tuple(self.client.app.dispatcher.groups):
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
            kwargs = {"chat_id": row["chat_id"]}
            if row.get("join_as"):
                try:
                    peer = await self.client.app.resolve_peer(row["join_as"])
                except RPCError:
                    await self.client.db.execute(
                        "UPDATE call.chats SET join_as = NULL WHERE chat_id = $1;",
                        row["chat_id"],
                    )
                else:
                    kwargs["config"] = GroupCallConfig(join_as=peer)

            try:
                await self.client.call.play(**kwargs)
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
            pattern.match(event.content).groups(),
        )
        if not chat_id:
            chat_id = event.chat.id
        else:
            try:
                chat = await event._client.get_chat(chat_id, False)
            except RPCError as e:
                await event.edit_text(
                    fmtmsg(
                        e.__class__.__name__,
                        e.MESSAGE.format(value=e.value),
                        fmtsec(now),
                    )
                )
                return
            else:
                chat_id = chat.id

        func, kwargs, text = None, {"chat_id": chat_id}, {"data": {"Chat ID": chat_id}}
        if action == "join":
            func = self.client.call.play
            text["head"] = "Joined Call"
            if join_as:
                try:
                    peer = await event._client.resolve_peer(join_as)
                except RPCError as e:
                    await event.edit_text(
                        fmtmsg(
                            e.__class__.__name__,
                            e.MESSAGE.format(value=e.value),
                            fmtsec(now),
                        )
                    )
                    return
                else:
                    join_as = get_channel_id(peer.channel_id)
                    text["data"]["Join as"] = join_as
                    kwargs["config"] = GroupCallConfig(join_as=peer)

            text["data"]["Mute"] = bool(mute)
        elif action == "leave":
            func = self.client.call.leave_call
            text["head"] = "Left Call"
        elif action == "start":
            func = event._client.create_video_chat
            text["head"] = "Started Call"
            if title:
                kwargs["title"] = title
                text["data"]["Title"] = title
        else:
            func = event._client.discard_group_call
            text["head"] = "Ended Call"

        try:
            await func(**kwargs)
        except RPCError as e:
            await event.edit_text(
                fmtmsg(
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

            await event.edit_text(fmtmsg(**text, foot=fmtsec(now)))

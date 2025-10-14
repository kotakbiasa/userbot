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
    Update,
)
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
from selfbot.utils import fmtsec, fmtstr, ids, ikm

QUERY = """
CREATE TABLE IF NOT EXISTS call (
    chat_id BIGINT  PRIMARY KEY,
    joined  BOOLEAN DEFAULT FALSE,
    mic_on  BOOLEAN DEFAULT FALSE,
    join_as BIGINT
);
"""

pattern = re.compile(
    r"^"
    r"(?P<action>(?:start|end|join|leave)?)call(?:s$)?"
    r"(?:\s+(?P<chat>@?[a-zA-Z][a-zA-Z0-9_]{3,32}|-100\d{10}))?"
    r"(?:\s+as@(?P<as>@?[a-z][a-zA-Z0-9_]{3,32}|-100\d{10}))?"
    r"(?:\s+(?P<mute>-mute))?"
    r"(?:\s+-t\s(?P<title>.+))?"
    r"$"
)


class Call(Module):
    name = "Call"

    cmds = "{action}?calls? {chat}? (as@{peer})? (-mute)? (-t {title})?"
    desc = {
        "action": "join|leave|start|end",
        "calls": "List Joined Chat IDs (Standalone)",
        "chat": "Chat ID or Username (Default: Current Chat)",
        "peer": "Chat ID or Username (Default: Self)",
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

        await self.client.db.execute(QUERY)
        rows = await self.client.db.fetch(
            """
            SELECT chat_id, join_as, mic_on
            FROM call
            WHERE joined IS TRUE;
            """
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
                continue
            else:
                if not row.get("mic_on"):
                    await self.client.tgc.mute(row["chat_id"])

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event)

    @listener.handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent("<code>...</code>"),
                )
            ],
            cache_time=0,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        await self.respond(event)

    async def respond(self, event: Update) -> None:
        text: str
        edit: callable

        chat_id: int
        join_as = None

        if isinstance(event, ChosenInlineResult):
            text = event.query
            edit = event.edit_message_text
            chat_id, _ = ids(event.inline_message_id)
        else:
            text = event.content
            edit = event.edit_text
            chat_id = event.chat.id

        now, (action, target, join_as, mute, title) = (
            datetime.datetime.now(),
            pattern.match(text).groupdict().values(),
        )
        if not action:
            return await edit(
                fmtstr(
                    "Call-Joined Chat IDs",
                    list(await self.client.tgc.calls),
                    fmtsec(now),
                ),
                reply_markup=ikm(("Close", b"0")),
            )

        if target:
            try:
                chat = await self.client.app.get_chat(target, False)
            except RPCError as e:
                return await edit(
                    fmtstr(
                        e.__class__.__name__,
                        e.MESSAGE.format(value=e.value),
                        fmtsec(now),
                    ),
                    reply_markup=ikm(("Close", b"0")),
                )
            else:
                chat_id = chat.id

        func: callable

        args = {"chat_id": chat_id}
        text = {"data": {"Chat": chat_id}}

        if action == "join":
            text["head"] = "Joined Call"
            text["data"]["Mute"] = bool(mute)
            if join_as:
                try:
                    peer = await self.client.app.resolve_peer(join_as)
                except RPCError as e:
                    return await edit(
                        fmtstr(
                            e.__class__.__name__,
                            e.MESSAGE.format(value=e.value),
                            fmtsec(now),
                        ),
                        reply_markup=ikm(("Close", b"0")),
                    )
                else:
                    join_as = get_channel_id(peer.channel_id)
                    text["data"]["Peer"] = join_as
                    args["config"] = GroupCallConfig(join_as=peer)

            func = self.client.tgc.play
        elif action == "leave":
            text["head"] = "Left Call"
            func = self.client.tgc.leave_call
        elif action == "start":
            text["head"] = "Started Call"
            if title:
                args["title"] = title
                text["data"]["Title"] = title

            func = self.client.app.create_video_chat
        else:
            text["head"] = "Ended Call"
            func = self.client.app.discard_group_call

        try:
            await func(**args)
        except RPCError as e:
            await edit(
                fmtstr(
                    e.__class__.__name__, e.MESSAGE.format(value=e.value), fmtsec(now)
                ),
                reply_markup=ikm(("Close", b"0")),
            )
        else:
            if action in ["join", "leave"]:
                if action == "join":
                    mic = self.client.tgc.mute if bool(mute) else self.client.tgc.unmute
                    await mic(chat_id)

                await self.client.db.execute(
                    """
                    INSERT INTO call (chat_id, joined, mic_on, join_as)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (chat_id) DO UPDATE SET
                        joined = EXCLUDED.joined,
                        mic_on = EXCLUDED.mic_on,
                        join_as = EXCLUDED.join_as;
                    """,
                    chat_id,
                    action == "join",
                    not bool(mute),
                    join_as,
                )

            if isinstance(event, Message):
                text["ext"] = f"/del_{event.id}"

            await edit(
                fmtstr(**text, foot=fmtsec(now)), reply_markup=ikm(("Close", b"0"))
            )

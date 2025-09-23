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

hide = False
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.pytgcalls_session import PyTgCallsSession
    from pytgcalls.types import GroupCallConfig
except Exception:
    hide = True
else:
    PyTgCallsSession.notice_displayed = True

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ids, ikm

pattern = re.compile(
    r"^"
    r"(?P<action>(?:start|end|join|leave))call"
    r"(?:\s+chat@(?P<chat>@?[a-z][a-zA-Z0-9_]{5,32}|-100\d{10}))?"
    r"(?:\s+as@(?P<as>@?[a-z][a-zA-Z0-9_]{5,32}|-100\d{10}))?"
    r"(?:\s+(?P<mute>-mute))?"
    r"(?:\s+-t\s(?P<title>.+))?"
    r"$"
)


class Call(Module):
    name = "Call"
    cmds = "{action(call)} *{(chat@) chat} *{(as@) as} *(-mute) *{(-t) title}"
    desc = {
        "action": "[join, leave, start, end]",
        "*": "Optional",
        "chat": "[username, chat_id]",
        "as": "[username, chat_id]",
        "title": "String",
    }

    async def on_starting(self) -> None:
        if hide:
            self.hide = True
            return self.client.unload(self)

        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

        self.client.tgc = PyTgCalls(self.client.app, 1, 1)
        await self.client.tgc.start()

        for group in self.client.app.dispatcher.groups.keys():
            if group == -1:
                continue

            for handler in self.client.app.dispatcher.groups[group]:
                await asyncio.to_thread(self.client.app.remove_handler, handler, group)

            self.client.app.dispatcher.groups.pop(group, None)

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        data = pattern.match(event.content).groupdict()
        data["chat_id"] = data["chat"] or event.chat.id
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
        action = pattern.match(event.query).groupdict()["action"].title()
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent(
                        f"<code>{action} Call...</code>"
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
        coro = None
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

            text["data"]["Mute"] = True if data["mute"] else False
            coro = self.client.tgc.play

        elif data["action"] == "leave":
            text["head"] = "Left Call"
            coro = self.client.tgc.leave_call

        elif data["action"] == "start":
            text["head"] = "Started Call"
            text["data"]["Title"] = "N/A"
            if data["title"]:
                text["data"]["Title"] = data["title"]
                args["title"] = data["title"]

            coro = self.client.app.create_video_chat

        else:
            text["head"] = "Ended Call"
            coro = self.client.app.discard_group_call

        try:
            await coro(**args)
        except Exception as e:
            await event.edit_message_text(
                f"<code>{e.__class__.__name__}</code>\n\n<b>{fmtsec(now)}</b>",
                reply_markup=ikm(("Close", b"0")),
            )
        else:
            if data["action"] == "join" and data["mute"]:
                self.client.loop.create_task(self.client.tgc.mute(data["chat_id"]))

            await event.edit_message_text(
                fmtstr(**text, foot=fmtsec(now)), reply_markup=ikm(("Close", b"0"))
            )

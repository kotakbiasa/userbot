import asyncio
import datetime
import inspect
import re

from pyrogram import filters
from pyrogram.enums import MessageEntityType
from pyrogram.errors import RPCError
from pyrogram.types import (
    ChatPermissions,
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

pattern = re.compile(
    r"^"
    r"(?P<action>(?:un)?(?:ban|mute)|kick)"
    r"(?:\s+(?P<target>(?!\d{1,2}[mhdw])(?!-r\s)[^\s]+))?"
    r"(?:\s+(?P<duration>\d{1,2})(?P<unit>[mhdw]))?"
    r"(?:\s+-r\s+(?P<reason>.+))?"
    r"$"
)


class Moderator(Module):
    name = "Moderator"
    cmds = "{action} {target} *{{n}{unit}} *{(-r) reason}"
    desc = {
        "action": "[ban, kick, mute, unban, unmute]",
        "target": "[user_id, username, reply_user]",
        "*": "Optional",
        "n": "[1-99]",
        "unit": "{m: minute, h: hour, d: day, w: week}",
        "reason": "String",
    }

    async def on_starting(self) -> None:
        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        data = pattern.match(event.content).groupdict()
        user = data["target"]
        if user:
            if (
                event.entities
                and event.entities[0].type == MessageEntityType.TEXT_MENTION
            ):
                data["target"] = event.entities[0].user.id
            else:
                try:
                    chat = await event._client.get_chat(user, False)
                except RPCError as e:
                    return await event.edit(f"<code>{e.__class__.__name__}</code>")
                else:
                    data["target"] = chat.id
        else:
            if event.reply_to_message and event.reply_to_message.from_user:
                data["target"] = event.reply_to_message.from_user.id
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

    @listener.handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        action = pattern.match(event.query).groupdict()["action"].title()
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent(
                        f"<code>{action} User...</code>"
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

        action, target = data["action"], data["target"]
        kwargs = {"chat_id": ids(event.inline_message_id)[0], "user_id": int(target)}

        unit, coro = "N/A", None
        if action in ["ban", "kick"]:
            coro = self.client.app.ban_chat_member
        elif action in ["mute", "unmute"]:
            coro = self.client.app.restrict_chat_member
            kwargs["permissions"] = ChatPermissions(
                **{
                    k: True if action == "unmute" else False
                    for k in inspect.signature(ChatPermissions).parameters
                }
            )
        else:
            coro = self.client.app.unban_chat_member

        if action != "kick":
            if "until_date" in inspect.signature(coro).parameters and data["duration"]:
                args = {self.period[data["unit"]]: int(data["duration"])}
                unit = "".join(
                    f"{v} {k.removesuffix('s').title() if v == 1 else k.title()}"
                    for k, v in args.items()
                )
                kwargs["until_date"] = datetime.datetime.now() + datetime.timedelta(
                    **args
                )
        else:
            kwargs["until_date"] = datetime.datetime.now() + datetime.timedelta(
                minutes=1
            )

        now = datetime.datetime.now()
        try:
            await coro(**kwargs)
        except RPCError as e:
            await event.edit_message_text(
                f"<code>{e.__class__.__name__}</code>\n\n<b>{fmtsec(now)}</b>",
                reply_markup=ikm(("Close", b"0")),
            )
        else:
            await event.edit_message_text(
                fmtstr(
                    f"<a href='tg://user?id={target}'>User</a> {self._past(action)}",
                    {"ID": target, "Reason": data["reason"] or "N/A", "Duration": unit},
                    fmtsec(now),
                ),
                reply_markup=ikm(("Close", b"0")),
            )

    @staticmethod
    def _past(text: str) -> str:
        result = text.removesuffix("e")
        if result.endswith("n"):
            result += "n"

        return f"{result}ed".title()

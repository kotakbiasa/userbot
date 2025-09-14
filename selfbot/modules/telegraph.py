import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)
from telegraph.aio import Telegraph as Graph

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm

pattern = re.compile(
    r"^graph(?:\s(?P<content>(?!-t\s.+).*?))?(?:\s-t\s(?P<title>.+))?$", re.DOTALL
)

spoiler = re.compile(r"</?spoiler\b[^>]*>")
emojiid = re.compile(r"<emoji id=\"\d+\">(.*?)</emoji>")
htmltag = re.compile(r"<.*?>")
mention = re.compile(r"(?<!\S)@([a-zA-Z0-9_]{5,32})(?!\S)")


class Telegraph(Module):
    name = "Telegraph"

    cmds = "graph *{-t title} {content}"
    desc = [
        "*      : Optional",
        "Title  : String",
        "Content: String or Reply to Content",
    ]

    async def on_startup(self) -> None:
        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

        self.graph = Graph(access_token=None, domain="graph.org")
        await self.graph.create_account(short_name=self.client.bot.me.username)

    @listener.handler(filters.regex(pattern), 1)
    async def on_message(self, event: Message) -> None:
        data = pattern.match(event.content.html).groupdict()

        if not data["content"]:
            if not event.reply_to_message.content:
                return await event.edit("<code>Reply to Content or Give a Text</code>")

            content = emojiid.sub(
                r"\1",
                spoiler.sub(
                    "",
                    mention.sub(
                        r"<a href='https://t.me/\1'>@\1</a>",
                        event.reply_to_message.content.html,
                    ),
                ),
            ).replace("\n", "<br>")

            if (
                event.reply_to_message.web_page
                and event.reply_to_message.web_page.photo
            ):
                content = f"{content}<img src='{event.reply_to_message.web_page.url}'>"

            data["content"] = content

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
                        "<code>Paste to Telegraph...</code>"
                    ),
                )
            ],
            cache_time=900,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_chosen_inline_result(self, event: ChosenInlineResult) -> None:
        if self.data.empty():
            return await self.client.app.delete_messages(
                *ids(event.inline_message_id), True
            )

        async with self.lock:
            data = await self.data.get()

        url = None
        now = datetime.datetime.now()

        try:
            res = await self.graph.create_page(
                data["title"] or "Untitled",
                html_content=data["content"],
                author_name="Telegraph",
                author_url="https://t.me/Telegraph",
            )
            url = res["url"]
        except Exception as e:
            await event.edit_message_text(
                f"<code>{e.__class__.__name__}</code>\n\n<b>{fmtsec(now)}</b>",
                reply_markup=ikm(("Close", b"0")),
            )
        else:
            await event.edit_message_text(
                fmtstr(
                    "Telegraph Page Created",
                    {
                        "Title": data["title"] or "N/A",
                        "Content": htmltag.sub("", data["content"])[:16],
                    },
                    fmtsec(now),
                ),
                reply_markup=ikm([("Copy", "copy", url), ("Open", "url", url)]),
            )

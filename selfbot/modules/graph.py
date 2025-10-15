import datetime
import re

from pyrogram import filters
from pyrogram.types import Message
from telegraph.aio import Telegraph

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(
    r"^graph(?:\s(?P<content>(?!-t\s.+).*?))?(?:\s-t\s(?P<title>.+))?$", re.DOTALL
)
spoiler = re.compile(r"</?spoiler\b[^>]*>")
emojiid = re.compile(r"<emoji id=\"\d+\">(.*?)</emoji>")
mention = re.compile(r"(?<!\S)@([a-zA-Z0-9_]{5,32})(?!\S)")


class Graph(Module):
    name = "Graph"

    cmds = "graph {content} (-t {title})?"
    desc = {
        "content": "String or Reply to Content",
        "title": "String",
        "?": "Optional",
        "e.g.": "graph Hello, World! -t Untitled",
    }

    graph: Telegraph

    async def on_starting(self) -> None:
        self.graph = Telegraph(access_token=None, domain="graph.org")
        await self.graph.create_account(short_name=self.client.bot.me.username)

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        content, title = pattern.match(event.content.html).groupdict().values()
        if not content:
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

        now = datetime.datetime.now()
        try:
            res = await self.graph.create_page(
                title or "Untitled",
                html_content=content,
                author_name="Telegraph",
                author_url="https://t.me/Telegraph",
            )
            url = res["url"]
        except Exception as e:
            await event.edit_text(fmtstr(e.__class__.__name__, str(e), fmtsec(now)))
        else:
            await event.edit_text(
                fmtstr(
                    "Graph Created",
                    {"Title": title or "Untitled", "URL": url},
                    fmtsec(now),
                )
            )

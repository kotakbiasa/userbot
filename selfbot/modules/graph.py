import datetime
import re

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import LinkPreviewOptions, Message
from telegraph.aio import Telegraph

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtmsg, fmtsec

pattern = re.compile(r"^graph(?:\s-t\s(.+))?$")


class Graph(Module):
    name = "Telegraph"
    cmds = "<Reply> graph (-t {title})?"
    desc = {
        "Reply": "Content",
        "title": "String",
        "?": "Optional",
        "e.g.": "<Reply> graph -t Hello, World!",
    }
    graph = None

    async def on_loading(self) -> None:
        self.graph = Telegraph(access_token=None, domain="graph.org")
        try:
            await self.graph.create_account(short_name=self.client.bot.me.username)
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            self.client.unload(self)

    @listener.handler(filters.regex(pattern) & listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        if not event.reply_to_message.content:
            await event.edit_text("<code>Reply to Content</code>")
            return

        await event.edit_text("<code>...</code>")
        content, (title,) = (
            event.reply_to_message.content.html.replace("\n", "<br>"),
            pattern.match(event.content).groups(),
        )
        content = re.sub(r"<emoji id=\"\d+\">(.*?)</emoji>", r"\1", content)
        content = re.sub(r"</?spoiler\b[^>]*>", "", content)
        content = re.sub(
            r"(?<!\S)@([a-zA-Z0-9_]{5,32})(?!\S)",
            r"<a href='https://t.me/\1'>@\1</a>",
            content,
        )
        if event.reply_to_message.web_page and event.reply_to_message.web_page.photo:
            img = event.reply_to_message.web_page.url
            if (
                event.reply_to_message.link_preview_options
                and event.reply_to_message.link_preview_options.show_above_text
            ):
                content = f"<img src='{img}'>{content}"
            else:
                content = f"{content}<img src='{img}'>"

        now = datetime.datetime.now(datetime.UTC)
        try:
            res = await self.graph.create_page(
                title or "Untitled",
                html_content=content,
                author_name="Telegraph",
                author_url="https://t.me/Telegraph",
            )
            url = res["url"]
        except Exception as e:
            await event.edit_text(fmtmsg(e.__class__.__name__, str(e), fmtsec(now)))
        else:
            if event.chat.type in (ChatType.PRIVATE, ChatType.BOT) or (
                event.chat.type not in (ChatType.PRIVATE, ChatType.BOT)
                and (
                    event.chat.admin_privileges
                    or (
                        event.chat.permissions
                        and event.chat.permissions.can_add_web_page_previews
                    )
                )
            ):
                await event.edit_text(
                    f"<b><blockquote>{fmtsec(now)}</blockquote></b>",
                    link_preview_options=LinkPreviewOptions(
                        is_disabled=False,
                        url=url,
                        prefer_small_media=True,
                        prefer_large_media=False,
                        show_above_text=True,
                    ),
                )
            else:
                await event.edit_text(
                    fmtmsg(
                        "Graph Page",
                        {"Link": url, "Title": title or "Untitled"},
                        fmtsec(now),
                    )
                )

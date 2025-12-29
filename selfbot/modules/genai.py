import asyncio
import base64
import collections
import datetime
import html
import re

from httpx import AsyncClient
from pyrogram import filters
from pyrogram.enums import MessageMediaType, ParseMode
from pyrogram.types import ChosenInlineResult, InlineQuery, Message, Sticker, Update

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, ikm

pattern = re.compile(r"^(?:(.+?)\s)?\!\?(?:\s-i)?$", flags=re.DOTALL)


class GenAI(Module):
    name = "Google Gemini"
    cmds = "{query} {infix} {suffix}?"
    desc = {
        "query": "String or <Reply or Quote>",
        "infix": "!?",
        "suffix": "-i (Ignore)",
        "?": "Optional",
        "e.g.": "Hello, World! !?",
    }

    async def on_loading(self) -> None:
        try:
            self.goog = AsyncClient(
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.client.config["GEMINI_API_KEY"],
                },
                http2=True,
                base_url="https://generativelanguage.googleapis.com",
            )
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            self.client.unload(self)
        else:
            self.data = collections.deque(maxlen=32)
            self.lock = asyncio.Lock()

    async def on_started(self) -> None:
        self.client.config.pop("GEMINI_API_KEY", None)

    async def on_closing(self) -> None:
        if hasattr(self, "goog") and not self.goog.is_closed:
            await self.goog.aclose()

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event)

    @listener.handler(filters.command("start"), 2)
    async def on_message_bot(self, event: Message) -> None:
        if (
            len(event.content.split()) == 2
            and event.content.split()[1].strip() == "clear"
        ):
            resp = await event.reply_sticker(
                self.client.config["STICKER_FILE_ID"],
                quote=True,
                reply_markup=ikm(("...", "switch_inline_query", "")),
            )
            async with self.lock:
                self.data.clear()
            await asyncio.gather(event.delete(), resp.delete())

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await self.answer(
            event, switch_pm_text="Clear Conversation", switch_pm_parameter="clear"
        )

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        await self.respond(event)

    async def gemini(self, model: str) -> str:
        try:
            resp = await self.goog.post(
                f"/v1beta/models/{model}:generateContent",
                json={"contents": list(self.data), "tools": [{"google_search": {}}]},
            )
            resp.raise_for_status()
        except Exception as e:
            return f"**{e.__class__.__name__}**:\n  `{e}`"
        else:
            try:
                json = resp.json()
                data = json["candidates"][0]["content"]
                text = data["parts"][0]["text"]
            except Exception as e:
                return f"**{e.__class__.__name__}**:\n  `{e}`"
            else:
                self.data.append(data)
                return text

    async def respond(self, event: Update) -> None:
        if isinstance(event, ChosenInlineResult):
            text, edit = event.query, event.edit_message_text
        else:
            text, edit = event.content, event.edit_text

        (query,), question = pattern.match(text).groups(), ""
        if query:
            question = f"```Query\n{query}```\n\n"
            await edit(question, parse_mode=ParseMode.MARKDOWN)
        else:
            if isinstance(event, ChosenInlineResult):
                await edit(
                    "<code>Give a Query with Suffix '!?'</code>",
                    reply_markup=ikm(("Close", b"0")),
                )
                return

            await edit("<code>...</code>")

        parts = []
        if query:
            parts.append({"text": query})

        if isinstance(event, Message):
            if event.quote and event.quote.text:
                parts.append({"text": event.quote.text})
            elif event.reply_to_message and event.reply_to_message.media:
                if event.reply_to_message.media in (
                    MessageMediaType.ANIMATION,
                    MessageMediaType.AUDIO,
                    MessageMediaType.DOCUMENT,
                    MessageMediaType.PHOTO,
                    MessageMediaType.STICKER,
                    MessageMediaType.VIDEO,
                    MessageMediaType.VOICE,
                ):
                    rep = event.reply_to_message
                    obj = getattr(rep, rep.media.value)
                    if obj.file_size > 32 * (1024**2):
                        await edit("<code>Exceeded Size (Limit: 32 MB)</code>")
                        return

                    mime = getattr(obj, "mime_type", "image/jpeg").lower().strip()
                    if isinstance(obj, Sticker) and obj.is_animated:
                        rep, mime = obj.thumbs[0].file_id, "image/jpeg"
                    elif mime.startswith("text"):
                        mime = "text/plain"

                    if not (
                        mime.startswith(("audio", "image", "text", "video"))
                        or mime == "application/pdf"
                    ):
                        await edit(
                            f"<code>Unsupported '{obj.mime_type}' MIME Type</code>"
                        )
                        return

                    parts.append(
                        {
                            "inline_data": {
                                "mime_type": mime,
                                "data": base64.b64encode(
                                    (
                                        await event._client.download_media(
                                            rep, in_memory=True
                                        )
                                    ).getvalue()
                                ).decode("ascii"),
                            }
                        }
                    )
                    if not query:
                        parts.append({"text": "Analyze"})
                elif event.reply_to_message.media == MessageMediaType.WEB_PAGE:
                    parts.append({"text": event.reply_to_message.content})
                else:
                    await edit(
                        f"<code>Unsupported {html.escape(f'<{event.reply_to_message.media}>')}</code>"
                    )
                    return
            elif (
                event.reply_to_message
                and event.reply_to_message.content
                and not event.content.endswith("-i")
            ):
                parts.append({"text": event.reply_to_message.content})
            elif not query:
                await edit(
                    f"<code>Give a Query or {html.escape('<Reply or Quote>')}</code>"
                )
                return

        ikb, now = [("Close", b"0")], datetime.datetime.now(datetime.UTC)
        async with self.lock:
            self.data.append({"role": "user", "parts": parts})
            res = await self.gemini(
                self.client.config.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
            )
            rtt = fmtsec(now)
            if len(res) > 2048:
                raw, url = await asyncio.gather(
                    event._client.parser.parse(res, ParseMode.MARKDOWN),
                    self.client.http.post("https://paste.rs", data=res.encode()),
                    return_exceptions=True,
                )
                res = f"{raw['message'][:1024]}..."
                if isinstance(event, ChosenInlineResult):
                    ikb.insert(0, ("Full", "url", f"{url.text.strip()}.md"))
                else:
                    rtt = f"[{rtt}]({url.text.strip()}.md)"

            await edit(
                f"{question}{res}\n\n> **{rtt}**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ikm(ikb),
            )

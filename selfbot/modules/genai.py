import asyncio
import base64
import collections
import datetime
import html
import re

from httpx import AsyncClient
from pyrogram import filters
from pyrogram.enums import MessageMediaType, ParseMode
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    Sticker,
    Update,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, ikm

pattern = re.compile(r"^(.*)?(?:\!\?)$", flags=re.DOTALL)


class GenAI(Module):
    name = "GenAI"

    cmds = "{query} !?"
    desc = {
        "query": "String or <Reply or Quote to Content>",
        "!?": "as Suffix",
        "e.g.": "Who are You? !?",
    }

    async def on_starting(self) -> None:
        if not self.client.config.get("gemini_api_key"):
            self.logger.warning("Gemini API_KEY None")
            return self.client.unload(self)

        self.lock = asyncio.Lock()
        self.data = collections.deque(maxlen=32)

        self.logger.info(f"Initializing {self.__class__.__name__}...")
        try:
            self.goog = AsyncClient(
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.client.config["gemini_api_key"],
                },
                timeout=45,
                base_url="https://generativelanguage.googleapis.com/v1beta",
            )
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            return self.client.unload(self)
        else:
            self.logger.info(f"{self.__class__.__name__} Initialized")

    async def on_stopping(self) -> None:
        if hasattr(self, "goog") and not self.goog.is_closed:
            self.logger.info(f"Closing {self.__class__.__name__}...")
            try:
                await self.goog.aclose()
            except Exception as e:
                self.logger.error(f"{e.__class__.__name__}: {e}")
            else:
                self.logger.info(f"{self.__class__.__name__} Closed")

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
                self.client.config["sticker_file_id"],
                quote=True,
                reply_markup=ikm(("...", "switch_inline_query", "")),
            )
            async with self.lock:
                self.data.clear()

            await asyncio.gather(event.delete(), resp.delete())

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent("<code>...</code>"),
                )
            ],
            switch_pm_text="Clear Conversation",
            switch_pm_parameter="clear",
        )

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        await self.respond(event)

    async def gemini(self, model: str = "gemini-2.5-flash") -> any:
        text = ""
        try:
            resp = await self.goog.post(
                f"/models/{model}:generateContent",
                json={"contents": list(self.data), "tools": [{"google_search": {}}]},
            )
            resp.raise_for_status()
        except Exception as e:
            return f"**{e.__class__.__name__}**:\n  `{e}`"
        else:
            data = resp.json()
            text = data["candidates"][0]["content"]
            return text["parts"][0]["text"]
        finally:
            if text:
                self.data.append(text)

    async def respond(self, event: Update) -> None:
        text = ""
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
                return await edit(
                    "<code>Give a Query with Suffix '!?'</code>",
                    reply_markup=ikm(("Close", b"0")),
                )

            await edit("<code>...</code>")

        parts = []
        if query:
            parts.append({"text": query})

        if not isinstance(event, ChosenInlineResult):
            if event.quote and event.quote.text:
                parts.append({"text": event.quote.text})
            elif event.reply_to_message and event.reply_to_message.media:
                if event.reply_to_message.media in [
                    MessageMediaType.ANIMATION,
                    MessageMediaType.AUDIO,
                    MessageMediaType.DOCUMENT,
                    MessageMediaType.PHOTO,
                    MessageMediaType.STICKER,
                    MessageMediaType.VIDEO,
                    MessageMediaType.VOICE,
                ]:
                    rep = event.reply_to_message
                    obj = getattr(rep, rep.media.value)
                    if obj.file_size > 32 * (1024**2):
                        return await edit("<code>Media too Large (Limit: 32 MB)</code>")

                    mime = getattr(obj, "mime_type", "image/jpeg").lower().strip()
                    if isinstance(obj, Sticker) and obj.is_animated:
                        rep, mime = obj.thumbs[0].file_id, "image/jpeg"
                    elif mime.startswith("text"):
                        mime = "text/plain"

                    if not (
                        mime.startswith(("audio", "image", "text", "video"))
                        or mime == "application/pdf"
                    ):
                        return await edit(
                            f"<code>Unsupported '{obj.mime_type}' MIME Type</code>"
                        )

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
                        parts.append(
                            {
                                "text": (
                                    "Analyze the media."
                                    " If there is readable text, extract it."
                                    " Summarize key details and provide brief context."
                                )
                            }
                        )
                elif event.reply_to_message.media == MessageMediaType.WEB_PAGE:
                    parts.append({"text": event.reply_to_message.content})
                else:
                    return await edit(
                        f"<code>Unsupported {html.escape(f'<{event.reply_to_message.media}>')}</code>"
                    )
            elif event.reply_to_message and event.reply_to_message.content:
                parts.append({"text": event.reply_to_message.content})
            elif not query:
                return await edit(
                    f"<code>Give a Query or {html.escape('<Reply or Quote to Content>')}</code>"
                )

        ikb, now = [("Close", b"0")], datetime.datetime.now(datetime.UTC)
        async with self.lock:
            self.data.append({"role": "user", "parts": parts})
            res = await self.gemini()
            rtt = fmtsec(now)
            if len(res) > 2048:
                url = (
                    await self.client.http.post("https://paste.rs", data=res.encode())
                ).text.strip()
                if isinstance(event, ChosenInlineResult):
                    res = f"{res[:1024]}..."
                    ikb.insert(0, ("Full", "url", f"{url}.markdown"))
                else:
                    res = f"{res[:1024]}[...]({url}.markdown)"

            await edit(
                f"{question}{res}\n\n> **{rtt}**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ikm(ikb),
            )

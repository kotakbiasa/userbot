import asyncio
import collections
import datetime
import html
import re

from httpx import AsyncClient
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
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
        "e.g.": "ask Who are You?",
    }

    async def on_starting(self) -> None:
        if not self.client.config.get("gemini_api_key"):
            return self.client.unload(self)

        self.genai = AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.client.config["gemini_api_key"],
            },
            timeout=45,
        )
        self.lock = asyncio.Lock()
        self.data = collections.deque(maxlen=32)

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
                reply_markup=ikm(("GenAI", "switch_inline_query", "")),
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
            cache_time=0,
            switch_pm_text="Clear Conversation",
            switch_pm_parameter="clear",
        )

    @listener.handler(filters.regex(pattern), 4)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        await self.respond(event)

    async def gemini(self, model: str = "gemini-2.5-flash") -> any:
        json = {"contents": list(self.data), "tools": [{"google_search": {}}]}
        text = None
        try:
            resp = await self.genai.post(f"/models/{model}:generateContent", json=json)
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
        edit = None
        if isinstance(event, ChosenInlineResult):
            text = event.query
            edit = event.edit_message_text
        else:
            text = event.content
            edit = event.edit_text

        (query,) = pattern.match(text).groups()
        question = ""
        if not query:
            if isinstance(event, ChosenInlineResult):
                return await edit(
                    "<code>Give a Query with Suffix '!?'</code>",
                    reply_markup=ikm(
                        [
                            ("GenAI", "switch_inline_query_current_chat", ""),
                            ("Close", b"0"),
                        ]
                    ),
                )

            if event.quote and event.quote.text:
                query = event.quote.text
            elif event.reply_to_message and event.reply_to_message.content:
                query = event.reply_to_message.content
            else:
                return await event.edit_text(
                    f"<code>Give a Query or {html.escape('<Reply or Quote to Content>')}</code>"
                )

            await edit("<code>...</code>")
        else:
            question = f"```Query\n{query}```\n\n"
            await edit(question, parse_mode=ParseMode.MARKDOWN)

        ikb = [[("GenAI", "switch_inline_query_current_chat", ""), ("Close", b"0")]]
        now = datetime.datetime.now(datetime.UTC)
        async with self.lock:
            self.data.append({"role": "user", "parts": [{"text": query}]})
            res = await self.gemini()
            rtt = fmtsec(now)
            if len(res) > 2048:
                link = (
                    await self.client.http.post("https://paste.rs", data=res.encode())
                ).text.strip()
                if isinstance(event, ChosenInlineResult):
                    ikb[0].insert(0, [("Output", "url", f"{link}.markdown")])
                    res = f"{res[:1024]}... TRUNCATED"
                else:
                    res = f"{res[:1024]}... [TRUNCATED]({link}.markdown)"

            await edit(
                f"{question}{res}\n\n> **{rtt}**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ikm(ikb),
            )

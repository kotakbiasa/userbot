import asyncio
import collections
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
    ReplyParameters,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import ids, ikm

pattern = re.compile(r"^(?:ask\s?)(.*)?", flags=re.DOTALL)


class GenAI(Module):
    name = "GenAI"

    cmds = "ask {query}?"
    desc = {"query": "String or <Reply or Quote to Content>", "?": "Optional"}

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

        self.data = asyncio.Queue()
        self.lock = asyncio.Lock()

        self.coll = collections.deque(maxlen=32)

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        (query,), args = pattern.match(event.content).groups(), {}

        if not query:
            if event.quote and event.quote.text:
                query = event.quote.text
                args = {
                    "quote": event.quote.text,
                    "quote_entities": event.quote.entities,
                    "quote_position": event.quote.position,
                }
            elif event.reply_to_message and event.reply_to_message.content:
                query = event.reply_to_message.content
            else:
                return await event.edit("<code>Reply to Content or Give a Text</code>")

            await event.delete(True)

        else:
            await event.edit(event.content.removeprefix("ask").lstrip())

        async with self.lock:
            await self.data.put(query)

        if event.external_reply and event.external_reply.message_id:
            args.update(
                {
                    "chat_id": event.external_reply.chat.id,
                    "message_id": event.external_reply.message_id,
                }
            )
        else:
            args.update(
                {
                    "chat_id": event.chat.id,
                    "message_id": event.reply_to_message_id or event.id,
                }
            )

        res = await event._client.get_inline_bot_results(self.client.bot.me.id, "ask")
        await event.reply_inline_bot_result(
            res.query_id, res.results[0].id, reply_parameters=ReplyParameters(**args)
        )

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
        query: str

        if self.data.empty():
            if len(event.query.split()) == 1:
                return await self.client.app.delete_messages(
                    *ids(event.inline_message_id), True
                )

            query = event.query.split(maxsplit=1)[1]
        else:
            async with self.lock:
                query = await self.data.get()

        async with self.lock:
            self.coll.append({"role": "user", "parts": [{"text": query}]})

        await event.edit_message_text(
            f"<code>{event.query.removeprefix("ask").lstrip()}</code>"
            if len(event.query.split()) > 1
            else "<code>Thinking...</code>"
        )

        keyb = [("Ask", "switch_inline_query_current_chat", "ask ")]
        resp = await self.gemini()
        if len(resp) > 2048:
            link = (
                await self.client.http.post("https://paste.rs", data=resp.encode())
            ).text.strip()
            keyb.insert(0, ("Full", "url", f"{link}.markdown"))
            resp = f"{resp[:1024]}... `[TRUNCATED]`"

        if len(event.query.split()) > 1:
            resp = f"```Question\n{event.query.removeprefix('ask').lstrip()}```\n{resp}"

        await event.edit_message_text(
            resp, parse_mode=ParseMode.MARKDOWN, reply_markup=ikm(keyb)
        )

    async def gemini(self, model: str = "gemini-2.5-flash") -> any:
        async with self.lock:
            payload = {"contents": list(self.coll), "tools": [{"google_search": {}}]}

        text = None
        try:
            resp = await self.genai.post(
                f"/models/{model}:generateContent", json=payload
            )
            resp.raise_for_status()
        except Exception as e:
            return f"{e.__class__.__name__}: {e}"
        else:
            data = resp.json()
            text = data["candidates"][0]["content"]
            return text["parts"][0]["text"]
        finally:
            if text:
                async with self.lock:
                    self.coll.append(text)

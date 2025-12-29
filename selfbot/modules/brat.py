import asyncio
import html
import io
import re

from httpx import AsyncClient
from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot import listener
from selfbot.module import Module


pattern = re.compile(r"^brat(?: (.+))?$", flags=re.DOTALL)


class Brat(Module):
    """
    Module for creating "brat" meme images using an external API.
    """

    name = "Brat"
    cmds = "<Reply to Message>? brat {text}?"
    desc = {
        "text": "Text to display on the brat image. Uses replied message text if empty.",
        "?": "Optional",
    }

    @listener.handler(filters.regex(pattern), priority=1)
    async def on_message_out(self, event: Message):
        """Handles the .brat command to generate an image."""
        text = (event.matches[0].group(1) or "").strip()

        if not text and event.reply_to_message:
            text = event.reply_to_message.text or event.reply_to_message.caption

        if not text:
            await event.edit_text("<code>Provide text or reply to a message.</code>")
            return

        # Saran: Pindahkan API Key ke environment variable untuk keamanan.
        # Contoh: BRAT_API_KEY="key_anda"
        # Lalu, muat di telegram.py dan akses via self.client.config.get("brat_api_key")
        api_key = self.client.config.get("brat_api_key", "key_iOPE5w") # Fallback ke key lama jika tidak ada
        if api_key == "key_iOPE5w":
            self.logger.warning("Using a hardcoded API key for the Brat module. Please set BRAT_API_KEY.")

        await event.edit_text("<code>Processing...</code>")
        api_url = "https://api.ferdev.my.id/maker/brat"
        params = {"text": text, "apikey": api_key}

        try:
            async with AsyncClient() as http_client:
                response = await http_client.get(api_url, params=params, timeout=20)
                response.raise_for_status()

            sticker_bytes = io.BytesIO(response.content)
            sticker_bytes.name = "brat.webp"
            await self.client.app.send_sticker(chat_id=event.chat.id, sticker=sticker_bytes, reply_to_message_id=event.reply_to_message_id or event.id)
            await event.delete()
        except Exception as e:
            self.logger.error(f"Brat module error: {e}")
            await event.edit_text(f"<b>Error:</b>\n<code>{html.escape(str(e))}</code>")
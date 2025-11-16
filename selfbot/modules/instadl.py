import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.types import InputMediaVideo, InputMediaPhoto

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

# Pola regex untuk mencocokkan URL Instagram
INSTA_URL_PATTERN = r"(https?://(?:www\.)?instagram\.com/[^\s]+)"

# Pola untuk perintah: .igdl <url> (tanpa reply) atau .igdl (dengan reply)
CMD_PATTERN = re.compile(rf"^(?:igdl|instadl)(?:\s+{INSTA_URL_PATTERN})?$")


class InstaDL(Module):
    name = "InstaDL"
    cmds = "igdl {url} or <Reply to Message> igdl"
    desc = {
        "Info": "Downloads media from an Instagram link using an external API.",
        "url": "The full URL of the Instagram post, reel, or story.",
        "e.g.": "igdl https://www.instagram.com/reel/C123...",
        "e.g. (reply)": "<Reply to a message with a link> igdl",
    }

    def _build_caption(self, metadata: dict, rtt: str) -> str:
        """Membangun caption untuk media yang diunduh."""
        caption_text = html.escape(metadata.get("caption", "No caption."))

        caption_parts = [
            f"<blockquote>{caption_text}</blockquote>"
        ]

        caption_parts.append(f"<b><blockquote>{rtt}</blockquote></b>")
        return "\n".join(caption_parts)

    async def _process_download(self, event: Message, url: str):
        """Memproses URL, mengunduh media, dan mengirimkannya."""
        now = datetime.datetime.now(datetime.UTC)
        api_url = "https://api.maher-zubair.tech/download/instagram"
        params = {"url": url}
        
        try:
            resp = await self.client.http.get(api_url, params=params, timeout=40)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != 200 or "result" not in data:
                error_message = data.get("message", "Unknown API error. The API might be down.")
                raise ValueError(error_message)

            result_data = data["result"]
            media_files = result_data.get("data", [])

            if not media_files:
                raise ValueError("No media found in the API response.")

            caption = self._build_caption(result_data, fmtsec(now))

            if len(media_files) > 1:
                # Handle album/carousel
                media_group = []
                for i, item in enumerate(media_files):
                    media_url = item["url"]
                    media_type = item.get("type", "image")
                    item_caption = caption if i == 0 else None  # Caption hanya di item pertama
                    if media_type == "video":
                        media_group.append(InputMediaVideo(media_url, caption=item_caption))
                    else:
                        media_group.append(InputMediaPhoto(media_url, caption=item_caption))
                await event.reply_media_group(media_group)
            else:
                # Handle single media
                first_media = media_files[0]
                download_url = first_media["url"]
                media_type = first_media.get("type", "image")
                if media_type == "video":
                    await event.reply_video(video=download_url, caption=caption)
                else:
                    await event.reply_photo(photo=download_url, caption=caption)
            
            await event.delete()

        except Exception as e:
            await event.edit_text(f"<b>Error:</b> <code>{html.escape(str(e))}</code>")

    @listener.handler(filters.regex(CMD_PATTERN), 1)
    async def on_message_out(self, event: Message) -> None:
        """Menangani perintah unduhan media Instagram."""
        match = CMD_PATTERN.match(event.text)
        url = match.group(1)

        if url:
            # Kasus 1: URL diberikan langsung di perintah
            await event.edit_text("<code>Processing Instagram link...</code>")
            await self._process_download(event, url)
        elif event.reply_to_message:
            # Kasus 2: Perintah adalah balasan ke pesan lain
            replied_text = event.reply_to_message.text or event.reply_to_message.caption
            if replied_text:
                url_match = re.search(INSTA_URL_PATTERN, replied_text)
                if url_match:
                    await event.edit_text("<code>Processing Instagram link from replied message...</code>")
                    await self._process_download(event, url_match.group(0))
                else:
                    await event.edit_text("<code>No Instagram link found in the replied message.</code>")
            else:
                await event.edit_text("<code>Replied message has no text to search for a link.</code>")
        else:
            await event.edit_text("<b>Usage:</b> <code>.igdl &lt;url&gt;</code> or reply to a message containing a link.")
import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message

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
        title = html.escape(metadata.get("title", "No caption"))
        username = html.escape(metadata.get("username", "N/A"))
        likes = metadata.get("likeCount", 0)
        comments = metadata.get("commentCount", 0)
        source = metadata.get("source")

        caption_parts = [
            f"<blockquote>{title}</blockquote>\n"
            f"<b>Author:</b> <a href=\"https://instagram.com/{username}\">@{username}</a>\n"
            f"<b>Likes:</b> {likes:,} | <b>Comments:</b> {comments:,}\n"
            f"<a href='{source}'>Source</a>"
        ]

        caption_parts.append(f"<b><blockquote>{rtt}</blockquote></b>")
        return "\n".join(caption_parts)

    async def _process_download(self, event: Message, url: str):
        """Memproses URL, mengunduh media, dan mengirimkannya."""
        now = datetime.datetime.now(datetime.UTC)
        api_url = "https://api.ferdev.my.id/downloader/instagram"
        params = {"link": url, "apikey": "key_iOPE5w"}
        
        try:
            resp = await self.client.http.get(api_url, params=params, timeout=40)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("success") or "data" not in data:
                error_message = data.get("message", "Unknown API error.")
                raise ValueError(error_message)

            media_data = data["data"]
            media_type = media_data.get("type")
            # API mengembalikan 'videoUrls' untuk video dan 'imageUrls' untuk gambar
            media_urls = media_data.get("videoUrls") or media_data.get("imageUrls", [])

            if not media_urls:
                raise ValueError("No media found in the API response.")

            download_url = media_urls[0]["url"]
            caption = self._build_caption(media_data.get("metadata", {}), fmtsec(now))

            if media_type == "video":
                await event.reply_video(video=download_url, caption=caption)
            else: # Asumsikan sebagai gambar jika bukan video
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
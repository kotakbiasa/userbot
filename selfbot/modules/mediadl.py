import asyncio
import datetime
import html
import os
import re
from pathlib import Path

import yt_dlp
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

# Regex to match 'dl' or 'mediadl' followed by a URL
pattern = re.compile(r"^(?:dl|mediadl)\s+(https?://[^\s]+)$")


class MediaDL(Module):
    name = "MediaDL"
    cmds = "dl {url}"
    desc = {
        "Info": "Downloads media from various sites using yt-dlp.",
        "url": "The URL of the media to download.",
        "e.g.": "dl https://www.tiktok.com/@user/video/12345",
    }

    def _format_number(self, num: int) -> str:
        """Formats a number into a human-readable string (e.g., 1.2M)."""
        if num is None:
            return ""
        if num < 1000:
            return str(num)
        if num < 1_000_000:
            return f"{num / 1000:.1f}K"
        if num < 1_000_000_000:
            return f"{num / 1_000_000:.1f}M"
        return f"{num / 1_000_000_000:.1f}B"

    def _build_caption(self, info: dict, rtt: str) -> str:
        """Builds the video caption according to the specified format."""
        description = html.escape(info.get("description") or info.get("title", "No Description"))
        source_url = info.get("webpage_url")

        # Caption parts
        caption_parts = []
        if description:
            caption_parts.append(f"<blockquote>{description}</blockquote>")
        
        if source_url:
            caption_parts.append(f"<a href='{source_url}'>Source</a>")

        caption_parts.append(f"<b><blockquote>{rtt}</blockquote></b>")

        return "\n".join(caption_parts)

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Handles the media download command."""
        await event.edit_text("<code>Downloading...</code>")
        now = datetime.datetime.now(datetime.UTC)

        match = pattern.match(event.text)
        url = match.group(1)

        output_path = Path("downloads") / f"{now.timestamp()}"
        output_path.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(output_path / '%(id)s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
            'max_filesize': 2000 * 1024 * 1024, # 2GB limit
        }

        def download_and_extract_info(url_to_dl):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_to_dl, download=True)
                return ydl.prepare_filename(info), info

        try:
            filepath, info = await asyncio.to_thread(download_and_extract_info, url)
            caption = self._build_caption(info, fmtsec(now))
            await event.reply_video(video=filepath, caption=caption)
            await event.delete()
        except Exception as e:
            await event.edit_text(f"<b>Error:</b> <code>{html.escape(str(e))}</code>")
        finally:
            if 'filepath' in locals() and os.path.exists(filepath):
                os.remove(filepath)
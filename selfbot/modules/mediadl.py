import asyncio
import datetime
import html
import httpx
import os
import re
import shutil
from pathlib import Path
from pyrogram import filters
from pyrogram.types import Message, InputMediaVideo, InputMediaPhoto

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtbyte

# Regex to match 'dl', 'mediadl', 'img', 'gallerydl' followed by a URL
pattern = re.compile(r"^(?:aio|dl)\s+(https?://[^\s]+)$")


class MediaDL(Module):
    name = "AIO Downloader"
    cmds = "aio|dl {url}"
    desc = {
        "Info": "Downloads media (video, audio, or images) from various sites.",
        "url": "The URL of the content to download.",
        "e.g.": "aio https://www.tiktok.com/@user/video/12345",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Handles media or image download command."""
        await event.edit_text("<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        match = pattern.match(event.text)
        url = match.group(1)

        download_dir = Path("downloads") / f"mediadl_{event.id}"
        download_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                await event.edit_text("<code>Fetching media info from API...</code>")
                api_url = f"https://chocomilk.amira.us.kg/v1/download/aio?url={url}"
                resp = await client.get(api_url)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "ok" or not data.get("result"):
                    raise Exception(f"API returned an error: {data.get('message', 'Unknown error')}")

                result = data["result"]
                title = result.get("title", "Untitled")
                media_items = result.get("medias", [])

                if not media_items:
                    # Fallback for single video/audio if 'medias' is not present
                    video_streams = result.get("video", [])
                    if video_streams:
                        best_stream = max(video_streams, key=lambda s: int(re.sub(r'\D', '', s.get("quality", "0")) or 0))
                        media_items.append(best_stream)

                if not media_items:
                    raise Exception("No media found in the API response.")

                await event.edit_text(f"<code>Downloading {len(media_items)} item(s)...</code>")

                downloaded_files = []
                for i, item in enumerate(media_items):
                    dlink = item.get("url")
                    if not dlink:
                        continue

                    file_ext = "mp4" if item.get("type") == "video" else "jpg"
                    file_path = download_dir / f"media_{i}.{file_ext}"

                    async with client.stream("GET", dlink, timeout=300) as stream_resp:
                        stream_resp.raise_for_status()
                        with open(file_path, "wb") as f:
                            async for chunk in stream_resp.aiter_bytes():
                                f.write(chunk)
                    downloaded_files.append({"path": file_path, "type": item.get("type", "video")})

                if not downloaded_files:
                    raise Exception("Failed to download any media files.")

                caption = f"<b>Title:</b> {html.escape(title)}\n"
                caption += f"<a href='{url}'>Source</a>\n\n"
                caption += f"<b><blockquote>{fmtsec(now)}</blockquote></b>"

                if len(downloaded_files) == 1:
                    media = downloaded_files[0]
                    if media["type"] == "video":
                        await event.reply_video(video=media["path"], caption=caption)
                    else:
                        await event.reply_photo(photo=media["path"], caption=caption)
                else:
                    album_media = []
                    for i, media in enumerate(downloaded_files):
                        is_first = i == 0
                        if media["type"] == "video":
                            album_media.append(InputMediaVideo(media["path"], caption=caption if is_first else None))
                        else:
                            album_media.append(InputMediaPhoto(media["path"], caption=caption if is_first
                                                               else None))
                    
                    # Send in chunks of 10
                    for i in range(0, len(album_media), 10):
                        chunk = album_media[i:i+10]
                        await event.reply_media_group(chunk)

            await event.delete()

        except Exception as e:
            error_msg = str(e)[:200]
            self.logger.error(f"MediaDL failed: {error_msg}")
            await event.edit_text(f"<b>Error:</b> <code>{html.escape(error_msg)}</code>")
        finally:
            if download_dir.exists():
                try:
                    shutil.rmtree(download_dir)
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup {download_dir}: {e}")
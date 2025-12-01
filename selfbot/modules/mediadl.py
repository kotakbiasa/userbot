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

    def _get_quality_score(self, quality_str: str) -> int:
        """Memberikan skor pada kualitas video untuk perbandingan."""
        if not isinstance(quality_str, str):
            return 0
        
        quality_str = quality_str.lower()
        score = 0
        
        # Ekstrak angka resolusi (misalnya, 720p -> 720)
        if match := re.search(r'(\d+)p', quality_str):
            score = int(match.group(1))
        
        # Beri bobot lebih untuk kualitas tanpa watermark
        if 'no_watermark' in quality_str:
            score += 10000  # Prioritas tinggi
        if 'hd' in quality_str:
            score += 1000   # Prioritas sedang
        if 'watermark' in quality_str:
            score -= 10000  # Prioritas rendah
            
        return score

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

                # Handle different API response structures (chocomilk vs ryzumi-like for IG)
                if data.get("success") and isinstance(data.get("data"), dict): # Instagram structure
                    result = data["data"]
                elif data.get("status") == "ok" and isinstance(data.get("result"), dict): # General structure
                    result = data["result"]
                else:
                    raise Exception(f"API returned an unrecognized error: {data.get('message', 'Unknown error')}")

                title = result.get("title", "Untitled")
                media_items = result.get("medias", [])

                if not media_items:
                    # Fallback for single video/audio if 'medias' is not present
                    video_streams = result.get("video", [])
                    if video_streams:
                        media_items.extend(video_streams)

                if not media_items:
                    raise Exception("No media found in the API response.")

                # Filter for best quality if multiple streams of the same type are present (e.g., FB HD/SD)
                video_streams = [m for m in media_items if m.get("type") == "video" and m.get("url")]
                image_streams = [m for m in media_items if m.get("type") == "image" and m.get("url")]

                final_media_items = []
                if video_streams:
                    best_video = max(video_streams, key=lambda s: self._get_quality_score(s.get("quality")))
                    final_media_items.append(best_video)
                final_media_items.extend(image_streams) # Add all images

                await event.edit_text(f"<code>Downloading {len(final_media_items)} item(s)...</code>")

                downloaded_files = []
                for i, item in enumerate(final_media_items):
                    dlink = item.get("url")
                    if not dlink:
                        continue

                    file_ext = "mp4" if item.get("type") == "video" else item.get("extension", "jpg")
                    file_path = download_dir / f"media_{i}.{file_ext}"

                    async with client.stream("GET", dlink, timeout=300) as stream_resp:
                        stream_resp.raise_for_status()
                        with open(file_path, "wb") as f:
                            async for chunk in stream_resp.aiter_bytes():
                                f.write(chunk)
                    downloaded_files.append({"path": file_path, "type": item.get("type", "video")})

                if not downloaded_files:
                    raise Exception("Failed to download any media files.")

                caption = f"<blockquote>{html.escape(title)}</blockquote>\n"
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
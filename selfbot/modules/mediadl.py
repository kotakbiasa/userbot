import asyncio
import datetime
import html
import os
import re
import shutil
from pathlib import Path

import yt_dlp
from httpx import AsyncClient
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtbyte

# Regex to match 'dl', 'mediadl', 'img', 'gallerydl' followed by a URL
pattern = re.compile(r"^(?:dl|mediadl|img|gallerydl)\s+(https?://[^\s]+)$")


class MediaDL(Module):
    name = "MediaDL"
    cmds = "dl|img {url}"
    desc = {
        "Info": "Downloads media (video/audio) or images from various sites.",
        "url": "The URL of the media or image gallery to download.",
        "e.g.": "dl https://www.tiktok.com/@user/video/12345 OR img https://www.instagram.com/p/ABC123/",
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

    async def _detect_content_type(self, url: str) -> str:
        """
        Detects content type by checking:
        1. URL pattern (faster)
        2. HTTP HEAD request (accurate)
        Returns 'image' or 'video'
        """
        # Fast check: URL pattern
        image_sites = [
            'instagram.com', 'twitter.com', 'x.com', 'flickr.com', 'pinterest.com',
            'deviantart.com', 'tumblr.com', '500px.com', 'pixiv.net', 'imgur.com',
        ]
        
        if any(site in url.lower() for site in image_sites):
            return 'image'

        # Untuk URL lain, cek dengan HEAD request
        try:
            async with AsyncClient(follow_redirects=True, timeout=10) as client:
                resp = await client.head(url)
                content_type = resp.headers.get('content-type', '').lower()
                
                if 'image' in content_type:
                    return 'image'
                elif 'video' in content_type or 'mp4' in content_type:
                    return 'video'
        except Exception as e:
            self.logger.warning(f"Failed to detect content type: {e}")

        # Default ke video jika tidak bisa deteksi
        return 'video'

    def _is_image_site(self, url: str) -> bool:
        """Detects if URL is from an image/gallery site."""
        image_sites = [
            'instagram.com', 'twitter.com', 'x.com', 'flickr.com', 'pinterest.com',
            'deviantart.com', 'tumblr.com', '500px.com', 'pixiv.net', 'imgur.com',
        ]
        return any(site in url.lower() for site in image_sites)

    def _download_with_gallerydl(self, url: str, output_dir: str) -> dict:
        """Download images using gallery-dl."""
        try:
            import gallery_dl
        except ImportError:
            raise Exception("gallery-dl not installed. Install with: pip install gallery-dl")

        config = {
            "output": {
                "directory": [output_dir],
                "filename": "{category}/{filename}",
            },
            "general": {
                "continue": True,
            },
        }
        
        job = gallery_dl.job.DownloadJob(url, kwdict=config)
        job.run()
        
        # Count files dan calculate total size
        total_files = 0
        total_size = 0
        
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                filepath = os.path.join(root, file)
                total_files += 1
                total_size += os.path.getsize(filepath)
        
        return {
            "file_count": total_files,
            "total_size": total_size,
            "output_dir": output_dir,
        }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Handles media or image download command."""
        await event.edit_text("<code>Detecting content type...</code>")
        now = datetime.datetime.now(datetime.UTC)

        match = pattern.match(event.text)
        url = match.group(1)
        
        # Auto-detect content type
        content_type = await self._detect_content_type(url)
        is_image = content_type == 'image'

        await event.edit_text("<code>Downloading...</code>")

        output_path = Path("downloads") / f"{now.timestamp()}"
        output_path.mkdir(parents=True, exist_ok=True)

        try:
            if is_image:
                # Download images using gallery-dl
                result = await asyncio.to_thread(
                    self._download_with_gallerydl, url, str(output_path)
                )

                file_count = result["file_count"]
                total_size = result["total_size"]

                if file_count == 0:
                    await event.edit_text("<code>No images found or download failed.</code>")
                    return

                caption = f"<b>Downloaded:</b> {file_count} file(s)\n<b>Size:</b> {fmtbyte(total_size)}\n<a href='{url}'>Source</a>\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"

                # Create zip if multiple files
                if file_count > 1:
                    zip_path = output_path.parent / f"gallery_{now.timestamp()}.zip"
                    await asyncio.to_thread(
                        shutil.make_archive,
                        str(zip_path.with_suffix('')),
                        'zip',
                        output_path
                    )
                    
                    await event.reply_document(
                        document=str(zip_path),
                        caption=caption,
                    )
                    
                    if zip_path.exists():
                        os.remove(zip_path)
                else:
                    # Send single image
                    image_file = list(output_path.rglob('*'))[0]
                    await event.reply_photo(
                        photo=str(image_file),
                        caption=caption,
                    )

                await event.delete()
            else:
                # Download video/audio using yt-dlp
                ydl_opts = {
                    'format': 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4][vcodec^=avc]/bestvideo[ext=mp4]+bestaudio/best',
                    'outtmpl': str(output_path / '%(id)s.%(ext)s'),
                    'quiet': True,
                    'noplaylist': True,
                    'max_filesize': 2000 * 1024 * 1024,
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4',
                    }],
                    'keepvideo': False,
                }

                def download_and_extract_info(url_to_dl):
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url_to_dl, download=True)
                        return ydl.prepare_filename(info), info

                filepath, info = await asyncio.to_thread(download_and_extract_info, url)
                caption = self._build_caption(info, fmtsec(now))
                await event.reply_video(video=filepath, caption=caption)
                await event.delete()

        except Exception as e:
            error_msg = str(e)[:200]
            self.logger.error(f"MediaDL failed: {error_msg}")
            await event.edit_text(f"<b>Error:</b> <code>{html.escape(error_msg)}</code>")
        finally:
            # Cleanup directory
            if output_path.exists():
                try:
                    shutil.rmtree(output_path)
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup {output_path}: {e}")
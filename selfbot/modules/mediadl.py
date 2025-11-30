import asyncio
import datetime
import html
import os
import re
import shutil
from pathlib import Path

import yt_dlp
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtbyte
from selfbot.utils.youtube_api import shell

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
            import gallery_dl.download
        except ImportError:
            raise Exception("gallery-dl not installed. Install with: pip install gallery-dl")

        try:
            # Use gallery-dl's download function directly
            pathfmt_list = gallery_dl.download.download([url], {
                "output": output_dir,
                "filename": "{category}/{filename}",
                "continue": True,
            })
            
        except Exception as e:
            raise Exception(f"gallery-dl download failed: {str(e)}")
        
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

    async def _convert_video_to_telegram_format(self, video_path: str) -> str:
        """
        Converts video to Telegram-compatible format (MP4 H.264 + AAC).
        Uses system FFmpeg directly.
        Returns path to converted video.
        """
        try:
            output_path = str(Path(video_path).with_stem(Path(video_path).stem + "_converted"))
            
            # FFmpeg command untuk convert ke format Telegram-compatible
            # H.264 codec, AAC audio, optimized untuk streaming
            command = (
                f"ffmpeg -i \"{video_path}\" "
                f"-c:v libx264 -preset fast -crf 23 "
                f"-c:a aac -b:a 128k "
                f"-movflags +faststart "
                f"\"{output_path}\" -y 2>&1"
            )
            
            self.logger.info(f"Converting video to Telegram format: {video_path}")
            stdout, stderr = await shell(command)
            
            # Check if output exists and is not empty
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise Exception("Video conversion failed or output is empty")
            
            # Remove original file to save space
            try:
                os.remove(video_path)
            except Exception as e:
                self.logger.warning(f"Failed to remove original video: {e}")
            
            return output_path
        except Exception as e:
            self.logger.error(f"Video conversion failed: {e}")
            raise Exception(f"Failed to convert video: {str(e)}")

    async def _is_video_telegram_compatible(self, video_path: str) -> bool:
        """
        Checks if video is Telegram-compatible (MP4 H.264 + AAC).
        Uses ffprobe to inspect video codec.
        """
        try:
            # Check video codec
            cmd_video = (
                f"ffprobe -v error -select_streams v:0 "
                f"-show_entries stream=codec_name "
                f"-of default=noprint_wrappers=1:nokey=1 \"{video_path}\""
            )
            stdout_v, _ = await shell(cmd_video)
            video_codec = stdout_v.strip() if isinstance(stdout_v, str) else stdout_v.decode().strip()
            
            # Check audio codec
            cmd_audio = (
                f"ffprobe -v error -select_streams a:0 "
                f"-show_entries stream=codec_name "
                f"-of default=noprint_wrappers=1:nokey=1 \"{video_path}\""
            )
            stdout_a, _ = await shell(cmd_audio)
            audio_codec = stdout_a.strip() if isinstance(stdout_a, str) else stdout_a.decode().strip()
            
            # Check if both are compatible
            is_h264 = "h264" in video_codec.lower()
            is_aac = "aac" in audio_codec.lower()
            is_mp4 = video_path.lower().endswith('.mp4')
            
            return is_h264 and is_aac and is_mp4
        except Exception as e:
            self.logger.warning(f"Failed to check video compatibility: {e}")
            # Jika check gagal, asumsikan perlu convert (safe approach)
            return False

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Handles media or image download command."""
        await event.edit_text("<code>Downloading...</code>")
        now = datetime.datetime.now(datetime.UTC)

        match = pattern.match(event.text)
        url = match.group(1)
        
        # Determine if it's an image site
        content_type = await self._detect_content_type(url)
        is_image = content_type == 'image'

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
                
                # Check if video needs conversion
                await event.edit_text("<code>Checking video format...</code>")
                is_compatible = await self._is_video_telegram_compatible(filepath)
                
                if not is_compatible:
                    await event.edit_text("<code>Converting video to Telegram format...</code>")
                    filepath = await self._convert_video_to_telegram_format(filepath)
                
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
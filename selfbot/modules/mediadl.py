import asyncio
import datetime
import html
import os
import re
import shutil
from pathlib import Path

from pyrogram import filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo, Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

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

    async def _run_ytdlp(self, url: str, download_dir: Path) -> tuple[str, str, int]:
        """Menjalankan yt-dlp untuk mengunduh media."""
        output_template = download_dir / "%(title).200s.%(ext)s"
        command = (
            f'yt-dlp -f "bv*+ba/b" --no-warnings --no-playlist '
            f'--remux-video mp4 -o "{output_template}" "{url}"'
        )

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        return stdout.decode(), stderr.decode(), process.returncode

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Handles media or image download command."""
        await event.edit_text("<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)
        match = pattern.match(event.text)
        url = match.group(1)

        download_dir = Path("downloads") / f"mediadl_{event.id}"
        download_dir.mkdir(parents=True, exist_ok=True)
        temp_dir_path = None

        try:
            temp_dir_path = download_dir
            await event.edit_text("<code>Downloading with yt-dlp...</code>")

            stdout, stderr, returncode = await self._run_ytdlp(url, download_dir)

            if returncode != 0 and not os.listdir(download_dir):
                error_details = stderr or stdout
                raise Exception(f"yt-dlp failed with code {returncode}:\n{error_details[:500]}")

            downloaded_files = sorted(
                [f for f in download_dir.iterdir() if f.is_file()],
                key=lambda p: p.stat().st_mtime,
            )

            if not downloaded_files:
                raise Exception("yt-dlp finished, but no files were downloaded.")

            title = downloaded_files[0].stem
            media_to_send = []
            for file_path in downloaded_files:
                ext = file_path.suffix.lower()
                if ext in [".mp4", ".mkv", ".webm"]:
                    media_to_send.append({"path": file_path, "type": "video"})
                elif ext in [".jpg", ".jpeg", ".png", ".webp"]:
                    media_to_send.append({"path": file_path, "type": "image"})
                else:
                    self.logger.info(f"Skipping unsupported file type: {ext}")

            if not media_to_send:
                raise Exception("No supported media files (video/image) found.")

            await event.edit_text(f"<code>Uploading {len(media_to_send)} item(s)...</code>")

            caption = (
                f"<blockquote>{html.escape(title)}</blockquote>\n"
                f"<a href='{url}'>Source</a>\n"
                f"<b><blockquote>{fmtsec(now)}</blockquote></b>"
            )

            if len(media_to_send) == 1:
                media = media_to_send[0]
                if media["type"] == "video":
                    await event.reply_video(video=media["path"], caption=caption)
                else:
                    await event.reply_photo(photo=media["path"], caption=caption)
            else:
                album_media = []
                for i, media in enumerate(media_to_send):
                    is_first = i == 0
                    current_caption = caption if is_first else None
                    if media["type"] == "video":
                        album_media.append(InputMediaVideo(media["path"], caption=current_caption))
                    else:
                        album_media.append(InputMediaPhoto(media["path"], caption=current_caption))

                # Kirim dalam potongan 10 media
                for i in range(0, len(album_media), 10):
                    chunk = album_media[i : i + 10]
                    await event.reply_media_group(chunk)

            await event.delete()

        except Exception as e:
            error_msg = str(e)[:200]
            self.logger.error(f"MediaDL failed: {error_msg}")
            await event.edit_text(
                f"<b>Error:</b> <code>{html.escape(str(e))}</code>"
            )
        finally:
            if temp_dir_path and temp_dir_path.exists():
                try:
                    # Gunakan asyncio.to_thread untuk operasi I/O yang memblokir
                    await asyncio.to_thread(shutil.rmtree, temp_dir_path)
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup {temp_dir_path}: {e}")
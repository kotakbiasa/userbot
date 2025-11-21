import asyncio
import datetime
import html
import os
import json
import re
import shutil
import time
import tempfile
import pathlib

import instaloader
from pyrogram import filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo, Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec


class SimpleRateController(instaloader.RateController):
    """A simple rate controller for instaloader to avoid blocking the event loop."""

    def __init__(self, context, sleep_time=2):
        super().__init__(context)
        self.sleep_time = sleep_time

    def sleep(self, secs):
        time.sleep(secs)

    def query_waittime(self, query_type, current_time, untracked_queries=False):
        return self.sleep_time

    def handle_429(self, query_type):
        self.sleep(self.query_waittime(query_type, time.time()))

    def count_per_sliding_window(self, query_type):
        return 1


class InstaDL(Module):
    name = "InstaDL"
    cmds = "instadl | igdl {url}"
    desc = {
        "Info": "Download an Instagram post, reel, or story.",
        "url": "The full URL of the Instagram content.",
        "e.g.": "igdl https://www.instagram.com/p/C7f3Z...",
        "vars": {
            "INSTAGRAM_USERNAME": "Your Instagram username (optional).",
            "INSTAGRAM_PASSWORD": "Your Instagram password (optional)."
        }
    }

    # Regex to match 'instadl' followed by a URL
    pattern = re.compile(r"^(?:instadl|igdl)\s+(https?://www\.instagram\.com/[^\s]+)$")

    async def on_loading(self):
        """Initializes the instaloader instance and session."""
        self.loader = instaloader.Instaloader(
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
            max_connection_attempts=3,
            request_timeout=30,
            rate_controller=lambda ctx: SimpleRateController(ctx, 2),
            quiet=True,
        )

        session_file = pathlib.Path("selfbot/.cache/instagram_session")
        await asyncio.to_thread(session_file.parent.mkdir, exist_ok=True)

        # Read credentials from config
        ig_user = self.client.config.get("INSTAGRAM_USERNAME")
        ig_pass = self.client.config.get("INSTAGRAM_PASSWORD")

        if not ig_user or not ig_pass:
            self.logger.info("Instagram: No credentials found, running in public mode.")
            return

        if await asyncio.to_thread(session_file.exists):
            try:
                await asyncio.to_thread(
                    self.loader.load_session_from_file, ig_user, str(session_file)
                )
                self.logger.info("Instagram: Loaded existing session file.")
                return
            except Exception:
                self.logger.warning("Instagram: Session file invalid, logging in fresh.")

        try:
            await asyncio.to_thread(self.loader.login, ig_user, ig_pass)
            await asyncio.to_thread(
                self.loader.save_session_to_file, str(session_file)
            )
            self.logger.info("Instagram: Logged in and saved new session file.")
        except Exception as e:
            self.logger.error(f"Instagram login failed: {e}")
            if await asyncio.to_thread(session_file.exists):
                await asyncio.to_thread(session_file.unlink)

    @staticmethod
    def _extract_shortcode(url: str) -> str | None:
        """Extracts the shortcode from an Instagram URL."""
        for pattern in (
            r"(?:https?://)?(?:www\.)?instagram\.com/p/([^/?#]+)",
            r"(?:https?://)?(?:www\.)?instagram\.com/reel/([^/?#]+)",
            r"(?:https?://)?(?:www\.)?instagram\.com/tv/([^/?#]+)",
            r"(?:https?://)?(?:www\.)?instagram\.com/stories/[^/]+/([^/?#]+)",
        ):
            if m := re.search(pattern, url):
                return m.group(1)
        return None

    async def _download_post(self, shortcode: str, url: str):
        """Downloads a post using instaloader."""
        temp_dir = await asyncio.to_thread(tempfile.mkdtemp, prefix="instadl_")
        self.loader.dirname_pattern = str(temp_dir)

        post = await asyncio.to_thread(
            instaloader.Post.from_shortcode, self.loader.context, shortcode
        )

        caption_text = post.caption or ""
        caption = f"<a href='{url}'>Source</a>"
        if caption_text:
            caption += f"\n\n<blockquote>{html.escape(caption_text)}</blockquote>"

        await asyncio.to_thread(self.loader.download_post, post, target="")

        media_files = await asyncio.to_thread(sorted, [
            f
            for f in pathlib.Path(temp_dir).glob("*")
            if f.suffix.lower() in {".mp4", ".jpg", ".jpeg", ".png"}
        ])
        if not media_files:
            raise ValueError("No media files found in downloaded content.")

        return media_files, caption, str(temp_dir)

    async def _send_album_chunks(self, event: Message, media_files: list, caption: str):
        """Sends a list of media files as an album, chunked into groups of 10."""
        MAX_ALBUM_SIZE = 10
        for i in range(0, len(media_files), MAX_ALBUM_SIZE):
            chunk = media_files[i : i + MAX_ALBUM_SIZE]
            album = []
            for idx, file_path in enumerate(chunk):
                is_first_item = i == 0 and idx == 0
                item_caption = caption if is_first_item else None
                if file_path.suffix.lower() == ".mp4":
                    album.append(InputMediaVideo(str(file_path), caption=item_caption))
                else:
                    album.append(InputMediaPhoto(str(file_path), caption=item_caption))

            await event._client.send_media_group(
                chat_id=event.chat.id,
                media=album,
                reply_to_message_id=event.reply_to_message_id or event.id,
            )

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Handles the .instadl command."""
        match = self.pattern.match(event.text)
        if not match:
            await event.edit_text("<b>Usage:</b> <code>.instadl &lt;url&gt;</code>")
            return

        url = match.group(1)
        now = datetime.datetime.now(datetime.UTC)
        await event.edit_text("<code>Downloading...</code>")

        media_files, caption, temp_dir = [], "", None
        try:
            shortcode = self._extract_shortcode(url)
            if not shortcode:
                raise ValueError("Invalid Instagram URL format.")

            media_files, caption, temp_dir = await self._download_post(shortcode, url)
            rtt = fmtsec(now)
            caption += f"\n\n<b><blockquote>{rtt}</blockquote></b>"

            if len(media_files) == 1:
                file_path = media_files[0]
                if file_path.suffix.lower() == ".mp4":
                    await event.reply_video(video=str(file_path), caption=caption)
                else:
                    await event.reply_photo(photo=str(file_path), caption=caption)
                await event.delete()
            elif len(media_files) > 1:
                await self._send_album_chunks(event, media_files, caption)
                await event.delete()
            else:
                await event.edit_text("<code>No media found to download.</code>")

        except Exception as e:
            self.logger.error(f"Instaloader failed: {e}. Trying fallback API.")
            await event.edit_text(f"<code>Instaloader failed. Trying fallback...</code>")
            # Fallback to gallery-dl
            try:
                temp_dir = await asyncio.to_thread(tempfile.mkdtemp, prefix="gdl_")
                
                process = await asyncio.create_subprocess_exec(
                    "gallery-dl",
                    "--write-metadata",
                    "-d", temp_dir,
                    url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_output = stderr.decode().strip()
                    self.logger.error(f"gallery-dl failed: {error_output}")
                    raise ValueError(f"gallery-dl error: {error_output}")

                media_files = await asyncio.to_thread(sorted, [
                    f for f in pathlib.Path(temp_dir).rglob('*') 
                    if f.is_file() and f.suffix.lower() in {".mp4", ".jpg", ".jpeg", ".png"}
                ])

                if not media_files:
                    raise ValueError("gallery-dl downloaded no media files.")

                # Try to find caption from metadata
                caption = ""
                for f in pathlib.Path(temp_dir).rglob('*.json'):
                    try:
                        meta = json.loads(await asyncio.to_thread(f.read_text))
                        caption_text = meta.get('caption') or meta.get('description', '')
                        caption = f"<a href='{url}'>Source</a>"
                        if caption_text:
                            caption += f"\n\n<blockquote>{html.escape(str(caption_text))}</blockquote>"
                        caption += f"\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"
                        break
                    except Exception:
                        continue  # Ignore parsing errors

                # Send the downloaded media
                if len(media_files) == 1:
                    file_path = media_files[0]
                    if file_path.suffix.lower() == ".mp4":
                        await event.reply_video(video=str(file_path), caption=caption)
                    else:
                        await event.reply_photo(photo=str(file_path), caption=caption)
                elif len(media_files) > 1:
                    await self._send_album_chunks(event, media_files, caption)
                await event.delete()

            except Exception as fallback_e:
                error_message = f"<b>Instaloader Error:</b>\n<code>{html.escape(str(e))}</code>\n\n<b>Fallback API Error:</b>\n<code>{html.escape(str(fallback_e))}</code>"
                await event.edit_text(error_message)
                return  # Stop execution if fallback also fails
        finally:
            if temp_dir and await asyncio.to_thread(os.path.exists, temp_dir):
                await asyncio.to_thread(shutil.rmtree, temp_dir)
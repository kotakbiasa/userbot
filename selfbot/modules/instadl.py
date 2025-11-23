import asyncio
import datetime
import html
import io
import re
import shutil
import tempfile
import time
from pathlib import Path

import instaloader
from pyrogram import filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo, Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

pattern = re.compile(r"^(?:igdl|instadl)\s+(https?://[^\s]+)$")

class SimpleRateController(instaloader.RateController):
    """A simple rate controller for instaloader to avoid blocking."""

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
    cmds = "igdl|instadl {url}"
    desc = {
        "Info": "Download an Instagram video/reel/photo.",
        "url": "The Instagram post URL.",
        "e.g.": "igdl https://www.instagram.com/p/C1234567890/",
    }

    async def on_loading(self) -> None:
        self.loader = None
        self.downloads_dir = Path("downloads")
        self.session_file = Path("instagram.session")

        await asyncio.to_thread(self.downloads_dir.mkdir, parents=True, exist_ok=True)

        ig_cfg = self.client.config.get("instagram", {})
        ig_user = ig_cfg.get("username")
        ig_pass = ig_cfg.get("password")

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

        if not ig_user or not ig_pass:
            self.logger.info("Instagram: No credentials found, running in public mode.")
            return

        if await asyncio.to_thread(self.session_file.exists):
            try:
                await asyncio.to_thread(self.loader.load_session_from_file, ig_user, str(self.session_file))
                self.logger.info("Instagram: Loaded existing session file.")
                return
            except Exception:
                self.logger.warning("Instagram: Session file invalid, logging in fresh.")

        try:
            await asyncio.to_thread(self.loader.login, ig_user, ig_pass)
            await asyncio.to_thread(self.loader.save_session_to_file, str(self.session_file))
            self.logger.info("Instagram: Logged in and saved new session file.")
        except Exception as e:
            self.logger.error(f"Instagram login failed: {e}")
            if await asyncio.to_thread(self.session_file.exists):
                await asyncio.to_thread(self.session_file.unlink)

    @staticmethod
    def _extract_shortcode(url: str) -> str | None:
        patterns = [
            r"(?:https?://)?(?:www\.)?instagram\.com/p/([^/?#]+)",
            r"(?:https?://)?(?:www\.)?instagram\.com/reel/([^/?#]+)",
            r"(?:https?://)?(?:www\.)?instagram\.com/tv/([^/?#]+)",
            r"(?:https?://)?(?:www\.)?instagram\.com/stories/[^/]+/([^/?#]+)",
        ]
        for pattern in patterns:
            if m := re.search(pattern, url):
                return m.group(1)
        return None

    async def _download_post(self, shortcode: str):
        temp_dir = self.downloads_dir / f"instagram_{shortcode}"
        await asyncio.to_thread(temp_dir.mkdir, parents=True, exist_ok=True)
        self.loader.dirname_pattern = str(temp_dir)

        post = await asyncio.to_thread(instaloader.Post.from_shortcode, self.loader.context, shortcode)

        caption = post.caption or ""
        if caption:
            caption = f"<blockquote>{html.escape(caption)}</blockquote>"

        await asyncio.to_thread(self.loader.download_post, post, target="")

        media_files = await asyncio.to_thread(lambda: [f for f in temp_dir.glob("*") if f.suffix.lower() in {".mp4", ".jpg", ".jpeg", ".png"}])
        if not media_files:
            raise ValueError("No media files found in downloaded content")

        return media_files, caption, temp_dir

    async def _send_album_chunks(self, chat_id, media_files, media_types, caption, reply_id):
        for i in range(0, len(media_files), 10):
            chunk_files = media_files[i : i + 10]
            chunk_types = media_types[i : i + 10]
            album = []
            for idx, file_path in enumerate(chunk_files):
                is_first = i == 0 and idx == 0
                media = InputMediaVideo if chunk_types[idx] == "video" else InputMediaPhoto
                album.append(media(file_path, caption=caption if is_first else None))
            await self.client.app.send_media_group(chat_id=chat_id, media=album, reply_to_message_id=reply_id)

    @listener.handler(filters.regex(pattern), priority=1)
    async def on_message_out(self, event: Message):
        match = pattern.match(event.text)
        if not match:
            await event.edit("Please provide an Instagram URL.")
            return

        url = match.group(1)
        await event.edit("<code>Downloading...</code>")
        now = datetime.datetime.now(datetime.UTC)

        shortcode = self._extract_shortcode(url)
        temp_dir_obj = None
        temp_dir_path = None

        try:
            if shortcode:
                media_files, caption, temp_dir_path = await self._download_post(shortcode)
                media_types = ["video" if f.suffix.lower() == ".mp4" else "image" for f in media_files]
            else:
                raise ValueError("Invalid Instagram URL format. Trying fallback API.")

        except Exception as e:
            self.logger.warning(f"Instaloader failed: {e}. Using fallback API.")
            await event.edit("<code>Instaloader failed, using fallback API...</code>")
            try:
                api_url = f"https://api.ryzumi.vip/api/downloader/igdl?url={url}"
                async with self.client.http.get(api_url, headers={"accept": "application/json"}) as resp:
                    if resp.status != 200:
                        raise Exception(f"Fallback API failed with HTTP {resp.status}")
                    data = await resp.json()

                if not data.get("status") or not data.get("data"):
                    raise Exception("Fallback API returned no data")

                temp_dir_obj = tempfile.TemporaryDirectory()
                temp_dir_path = Path(temp_dir_obj.name)
                media_files = []
                media_types = []

                for item in data["data"]:
                    file_url = item.get("url")
                    if not file_url:
                        continue

                    file_type = item.get("type", "").lower()
                    filename = Path(file_url.split("?")[0]).name
                    if not Path(filename).suffix:
                        filename += ".mp4" if file_type == "video" else ".jpg"

                    tmp_path = temp_dir_path / filename
                    async with self.client.http.get(file_url) as file_resp:
                        if file_resp.status != 200:
                            continue
                        content = await file_resp.read()
                        await asyncio.to_thread(tmp_path.write_bytes, content)

                    media_files.append(str(tmp_path))
                    media_types.append(file_type)

                caption = (data["data"][0].get("caption") or "").strip()
                if caption:
                    caption = f"<blockquote>{html.escape(caption)}</blockquote>"

            except Exception as fallback_e:
                await event.edit(f"<b>Error:</b> Both download methods failed.\n<b>Instaloader:</b> <code>{html.escape(str(e))}</code>\n<b>Fallback:</b> <code>{html.escape(str(fallback_e))}</code>")
                return

        try:
            if not media_files:
                await event.edit("Could not find any media to download.")
                return

            rtt = fmtsec(now)
            caption_parts = []
            if caption:
                caption_parts.append(caption)
            
            # Menambahkan link source
            caption_parts.append(f"<a href='{url}'>Source</a>")
            
            # Menambahkan timestamp
            caption_parts.append(f"<b><blockquote>{rtt}</blockquote></b>")
            final_caption = "\n\n".join(caption_parts)

            if len(media_files) == 1:
                media_type = media_types[0]
                file_path = media_files[0]
                media_to_send = (
                    InputMediaVideo(file_path, caption=final_caption)
                    if media_type == "video" else
                    InputMediaPhoto(file_path, caption=final_caption)
                )
                if media_type == "video":
                    await event.edit_media(media_to_send)
                else:
                    await event.edit_media(media_to_send)
            else:
                # For albums, we reply to the original message and delete the command message
                reply_to = (
                    event.reply_to_message.id if event.reply_to_message else event.id
                )
                await self._send_album_chunks(event.chat.id, media_files, media_types, final_caption, reply_to)
                await event.delete()
        finally:
            if temp_dir_path:
                await asyncio.to_thread(shutil.rmtree, temp_dir_path, ignore_errors=True)
            if temp_dir_obj:
                temp_dir_obj.cleanup()
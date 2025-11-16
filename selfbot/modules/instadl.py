import asyncio
import html
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


class SimpleRateController(instaloader.RateController):
    """A simple rate controller for Instaloader to avoid blocking."""

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
    """Module to download Instagram posts, reels, and stories."""

    name = "InstaDL"
    cmds = "instadl {url}"
    desc = {
        "url": "Link to the Instagram post, reel, or story.",
        "e.g.": "instadl https://www.instagram.com/p/C...",
    }

    # Regex to capture the command and URL
    pattern = re.compile(r"^instadl\s+(https?://(?:www\.)?instagram\.com/.+)", re.IGNORECASE)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loader = None
        self.downloads_dir = Path("downloads")
        self.session_file = Path(".instaloader_session")
        self.ig_user = self.client.config.get("instagram_username")
        self.ig_pass = self.client.config.get("instagram_password")
        self._session_state = "uninitialized"        

    async def on_starting(self):
        """Initializes the Instaloader instance and logs in."""
        self.logger.info("Initializing Instaloader...")
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        if self.loader: # Already initialized
            return
            
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

        if not self.ig_user or not self.ig_pass:
            self.logger.info("Instagram: No credentials found. Running in public mode.")
            self._session_state = "public"
            return

        if self.session_file.exists():
            try:
                await asyncio.to_thread(
                    self.loader.load_session_from_file, self.ig_user, str(self.session_file)
                )
                self.logger.info("Instagram: Loaded existing session file.")
                self._session_state = "session"
                return
            except Exception as e:
                self.logger.warning(f"Instagram: Session file invalid, logging in fresh. Error: {e}")

        try:
            await asyncio.to_thread(self.loader.login, self.ig_user, self.ig_pass)
            await asyncio.to_thread(
                self.loader.save_session_to_file, str(self.session_file)
            )
            self.logger.info("Instagram: Logged in and saved new session file.")
            self._session_state = "logged_in"
        except Exception as e:
            self.logger.error(f"Instagram login failed: {e}")
            if self.session_file.exists():
                self.session_file.unlink()
            self._session_state = "public"

    @staticmethod
    def _extract_shortcode(url: str) -> str | None:
        """Extracts the shortcode from an Instagram URL."""
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
        """Downloads a post and returns file paths and caption."""
        temp_dir_path = self.downloads_dir / f"instagram_{shortcode}"
        await asyncio.to_thread(temp_dir_path.mkdir, parents=True, exist_ok=True)
        self.loader.dirname_pattern = str(temp_dir_path)

        post = await asyncio.to_thread(
            instaloader.Post.from_shortcode, self.loader.context, shortcode
        )

        caption = post.caption or ""
        if caption:
            caption = f"<blockquote>{html.escape(caption)}</blockquote>"

        await asyncio.to_thread(self.loader.download_post, post, target="")

        media_files = [
            f
            for f in temp_dir_path.glob("*")
            if f.suffix.lower() in {".mp4", ".jpg", ".jpeg", ".png"}
        ]
        if not media_files:
            raise ValueError("No media files found in downloaded content.")

        return media_files, caption, temp_dir_path

    async def _send_album_chunks(self, chat_id, media_files, media_types, caption, reply_id):
        """Sends media files in chunks of 10."""
        MAX_ALBUM = 10
        for i in range(0, len(media_files), MAX_ALBUM):
            chunk_files = media_files[i : i + MAX_ALBUM]
            chunk_types = media_types[i : i + MAX_ALBUM]
            album = []
            for idx, file_path in enumerate(chunk_files):
                is_first = i == 0 and idx == 0
                media_caption = caption if is_first else None
                if chunk_types[idx] == "video":
                    album.append(InputMediaVideo(str(file_path), caption=media_caption))
                else:
                    album.append(InputMediaPhoto(str(file_path), caption=media_caption))
            await self.client.app.send_media_group(
                chat_id=chat_id, media=album, reply_to_message_id=reply_id
            )

    @listener.handler(filters.regex(pattern), priority=1)
    async def on_message_out(self, event: Message):
        """Handles the .instadl command."""
        url = event.matches[0].group(1).strip()
        if not url:
            await event.edit_text("<code>Please provide an Instagram URL.</code>")
            return

        await event.edit_text("<code>Downloading...</code>")

        shortcode = self._extract_shortcode(url)
        temp_dir = None
        media_files = []
        media_types = []
        caption = ""

        try:
            # First attempt with Instaloader
            if shortcode and self._session_state != "uninitialized":
                try:
                    files, caption, temp_dir = await self._download_post(shortcode)
                    media_files = files
                    media_types = ["video" if f.suffix.lower() == ".mp4" else "image" for f in media_files]
                except Exception as e:
                    self.logger.warning(f"Instaloader failed: {e}. Falling back to API.")
                    media_files = [] # Reset to trigger fallback

            # Fallback to API if Instaloader fails or is not applicable
            if not media_files:
                api_url = f"https://api.ryzumi.vip/api/downloader/igdl?url={url}"
                async with self.client.http.get(api_url, headers={"accept": "application/json"}) as resp:
                    if resp.status_code != 200:
                        raise ConnectionError(f"API failed with HTTP {resp.status_code}")
                    data = await resp.json()

                if not data.get("status") or not (api_data := data.get("data")):
                    raise ValueError("API returned no valid data.")

                temp_dir_obj = tempfile.TemporaryDirectory()
                temp_dir = Path(temp_dir_obj.name)

                for item in api_data:
                    file_url = item.get("url")
                    if not file_url:
                        continue

                    file_type = item.get("type", "").lower()
                    filename = file_url.split("?")[0].split("/")[-1]
                    if "." not in filename:
                        filename += ".mp4" if file_type == "video" else ".jpg"

                    tmp_path = temp_dir / filename
                    async with self.client.http.get(file_url) as file_resp:
                        if file_resp.status_code != 200:
                            self.logger.warning(f"Failed to download {file_url}: HTTP {file_resp.status_code}")
                            continue
                        await asyncio.to_thread(tmp_path.write_bytes, await file_resp.aread())

                    media_files.append(tmp_path)
                    media_types.append(file_type)

                if api_data[0].get("caption"):
                    caption = f"<blockquote>{html.escape(api_data[0]['caption'])}</blockquote>"

            if not media_files:
                raise ValueError("Failed to download media from all sources.")

            # Send the downloaded media
            reply_id = event.reply_to_message_id or event.id
            if len(media_files) == 1:
                file_path = str(media_files[0])
                if media_types[0] == "video":
                    await self.client.app.send_video(event.chat.id, file_path, caption=caption, reply_to_message_id=reply_id)
                else:
                    await self.client.app.send_photo(event.chat.id, file_path, caption=caption, reply_to_message_id=reply_id)
                await event.delete()
            else:
                await self._send_album_chunks(event.chat.id, media_files, media_types, caption, reply_id)
                await event.delete()

        except Exception as e:
            self.logger.error(f"InstaDL error: {e}")
            await event.edit_text(f"<b>Error:</b>\n<code>{html.escape(str(e))}</code>")

        finally:
            # Clean up the temporary directory
            if temp_dir:
                try:
                    await asyncio.to_thread(shutil.rmtree, temp_dir)
                except Exception as e:
                    self.logger.error(f"Failed to clean up temp directory {temp_dir}: {e}")
import asyncio
import datetime
import html
import re
import tempfile
from pathlib import Path

from pyrogram import filters
from pyrogram.types import InputMediaVideo, Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

pattern = re.compile(r"^(?:fb|facebookdl)\s+(https?://[^\s]+)$")


class FacebookDL(Module):
    name = "FacebookDL"
    cmds = "fb|facebookdl {url}"
    desc = {
        "Info": "Download a Facebook video.",
        "url": "The Facebook video URL.",
        "e.g.": "fb https://www.facebook.com/watch/?v=1234567890",
    }

    @listener.handler(filters.regex(pattern), priority=1)
    async def on_message_out(self, event: Message):
        match = pattern.match(event.text)
        if not match:
            await event.edit("Please provide a Facebook URL.")
            return

        url = match.group(1)
        await event.edit("<code>Downloading...</code>")
        now = datetime.datetime.now(datetime.UTC)

        temp_dir_obj = None

        try:
            api_url = f"https://api.ryzumi.vip/api/downloader/fbdl?url={url}"

            resp = await self.client.http.get(api_url, headers={"accept": "application/json"})
            if resp.status_code != 200:
                raise Exception(f"API failed with HTTP {resp.status_code}")
            data = resp.json()

            if not data.get("status") or not data.get("data"):
                error_message = data.get("message", "API returned no data or failed status.")
                raise Exception(error_message)

            api_data = data["data"]
            if not isinstance(api_data, list):
                raise Exception("API returned invalid data format.")

            video_url = None
            # Prioritaskan resolusi HD, lalu ambil video pertama yang tersedia jika tidak ada HD
            for item in api_data:
                if item.get("type") == "video" and "hd" in item.get("resolution", "").lower() and not item.get("shouldRender"):
                    video_url = item.get("url")
                    break
            
            if not video_url:
                video_url = next((item.get("url") for item in api_data if item.get("type") == "video" and not item.get("shouldRender")), None)

            if not video_url:
                raise Exception("No downloadable video URL found in API response.")

            title = video_data.get("title", "Unknown Title").strip()

            temp_dir_obj = tempfile.TemporaryDirectory()
            temp_dir_path = Path(temp_dir_obj.name)
            
            file_path = temp_dir_path / "video.mp4"

            file_resp = await self.client.http.get(video_url)
            if file_resp.status_code != 200:
                raise Exception(f"Failed to download video file (HTTP {file_resp.status_code})")
            content = file_resp.content
            await asyncio.to_thread(file_path.write_bytes, content)

            rtt = fmtsec(now)
            caption_parts = [
                f"<a href='{url}'>Source</a>",
                f"<b><blockquote>{rtt}</blockquote></b>"
            ]

            media_to_send = InputMediaVideo(str(file_path), caption="\n".join(caption_parts))
            await event.edit_media(media_to_send)

        except Exception as e:
            self.logger.error(f"FacebookDL failed: {e}")
            await event.edit(f"<b>Error:</b> Failed to download Facebook video.\n<b>Reason:</b> <code>{html.escape(str(e))}</code>")
        finally:
            if temp_dir_obj:
                temp_dir_obj.cleanup()
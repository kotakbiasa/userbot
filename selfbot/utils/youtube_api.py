import asyncio
import os
import re
from typing import Union

from yt_dlp import YoutubeDL
from youtubesearchpython.__future__ import VideosSearch


async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        if "unavailable videos are hidden" in (errorz.decode("utf-8")).lower():
            return out.decode("utf-8")
        else:
            return errorz.decode("utf-8")
    return out.decode("utf-8")


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\-_]|\[[0-?]*[ -/]*[@-~])")
        self.ydl_opts_audio = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "geo_bypass": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
        }

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def details(self, link: str, videoid: Union[bool, str] = None):
        """Gets detailed information for a video."""
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        try:
            results = VideosSearch(link, limit=1)
            result = (await results.next())["result"]
            if not result:
                return None

            video = result[0]
            title = video.get("title", "N/A")
            duration_min = video.get("duration")
            thumbnail = video.get("thumbnails", [{}])[0].get("url", "").split("?")[0]
            vidid = video.get("id")
            
            # Convert duration to seconds
            duration_sec = 0
            if duration_min:
                parts = list(map(int, duration_min.split(':')))
                if len(parts) == 3: # H:M:S
                    duration_sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
                elif len(parts) == 2: # M:S
                    duration_sec = parts[0] * 60 + parts[1]
                elif len(parts) == 1: # S
                    duration_sec = parts[0]

            return {
                "title": title,
                "duration_min": duration_min,
                "duration_sec": duration_sec,
                "thumbnail": thumbnail,
                "id": vidid,
                "link": video.get("link")
            }
        except Exception:
            return None

    async def search(self, query: str, limit: int = 5):
        """Searches youtube and returns a list of results."""
        try:
            results = VideosSearch(query, limit=limit)
            result = (await results.next())["result"]
            return result
        except Exception:
            return []

    async def track(self, link: str, videoid: Union[bool, str] = None):
        """Gets track details for downloading."""
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        results = VideosSearch(link, limit=1)
        result = (await results.next())["result"]
        if not result:
            return None, None

        video = result[0]
        track_details = {
            "title": video.get("title"),
            "link": video.get("link"),
            "vidid": video.get("id"),
            "duration_min": video.get("duration"),
            "thumb": video.get("thumbnails", [{}])[0].get("url", "").split("?")[0],
        }
        return track_details, video.get("id")

    async def download(self, link: str) -> str:
        """Downloads the best audio of a given YouTube link."""
        loop = asyncio.get_running_loop()

        def audio_dl():
            with YoutubeDL(self.ydl_opts_audio) as ydl:
                info = ydl.extract_info(link, download=False)
                download_path = os.path.join("downloads", f"{info['id']}.{info.get('ext', 'm4a')}")
                if os.path.exists(download_path):
                    return download_path
                ydl.download([link])
                return download_path

        downloaded_file = await loop.run_in_executor(None, audio_dl)
        return downloaded_file
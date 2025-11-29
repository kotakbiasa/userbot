# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import os
import re
import yt_dlp
import random
import logging
import asyncio
import aiohttp
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass

from pyrogram import enums, types
from py_yt import Playlist, VideosSearch


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class Track:
    id: str
    title: str
    duration: str
    duration_sec: int
    thumbnail: str
    url: str
    channel_name: str
    view_count: str
    message_id: Optional[int] = None
    user: Optional[str] = None
    video: bool = False


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.warned = False
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

    def get_cookies(self):
        cookie_dir = Path("cookies")
        cookie_dir.mkdir(exist_ok=True)
        if not self.checked:
            for file in os.listdir(cookie_dir):
                if file.endswith(".txt"):
                    self.cookies.append(file)
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("File cookie tidak ditemukan di folder 'cookies/'. Proses unduh mungkin gagal.")
            return None
        return str(cookie_dir / random.choice(self.cookies))

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Menyimpan file cookie dari URL...")
        cookie_dir = Path("cookies")
        cookie_dir.mkdir(exist_ok=True)

        # Hapus cookie lama sebelum menyimpan yang baru
        for old_cookie in cookie_dir.glob("*.txt"):
            try:
                old_cookie.unlink()
            except OSError as e:
                logger.error(f"Gagal menghapus cookie lama {old_cookie}: {e}")

        async with aiohttp.ClientSession() as session:
            for url in urls:
                path = cookie_dir / f"cookie{random.randint(10000, 99999)}.txt"
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    with open(path, "wb") as fw:
                        fw.write(await resp.read())
        logger.info("Cookies saved.")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def url(self, message_1: types.Message) -> Union[str, None]:
        messages = [message_1]
        link = None
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        for message in messages:
            text = message.text or message.caption or ""

            if message.entities:
                for entity in message.entities:
                    if entity.type == enums.MessageEntityType.URL:
                        link = text[entity.offset : entity.offset + entity.length]
                        break

            if message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == enums.MessageEntityType.TEXT_LINK:
                        link = entity.url
                        break

        if link:
            return link.split("&si")[0].split("?si")[0]
        return None

    @staticmethod
    def to_seconds(duration: str) -> int:
        """Mengubah durasi format H:M:S atau M:S atau S ke detik."""
        if not duration or not isinstance(duration, str):
            return 0
        parts = list(map(int, duration.split(':')))
        if len(parts) == 3:  # H:M:S
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:  # M:S
            return parts[0] * 60 + parts[1]
        return parts[0]  # S

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        _search = VideosSearch(query, limit=1)
        results = await _search.next()
        if results and results["result"]:
            data = results["result"][0]
            return Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=data.get("duration"),
                duration_sec=self.to_seconds(data.get("duration")),
                message_id=m_id,
                title=data.get("title")[:25],
                thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                video=video,
            )
        return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=self.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails")[-1].get("url").split("?")[0],
                    url=data.get("link").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except:
            pass
        return tracks

    async def download(self, video_id: str, video: bool = False) -> Optional[str]:
        url = self.base + video_id
        download_dir = Path("downloads")
        download_dir.mkdir(exist_ok=True)
        ext = "mp4" if video else "webm"
        filename = download_dir / f"{video_id}.{ext}"

        if filename.exists():
            return str(filename)

        cookie = self.get_cookies()
        base_opts = {
            "outtmpl": str(download_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "nocheckcertificate": True,
            "cookiefile": cookie,
        }

        if video:
            ydl_opts = {
                **base_opts,
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
                "merge_output_format": "mp4",
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio[ext=webm][acodec=opus]",
            }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError):
                    if cookie in self.cookies:
                        self.cookies.remove(cookie)
                    return None
                except Exception as ex:
                    logger.error("Download failed: %s", ex)
                    return None
            return str(filename)

        return await asyncio.to_thread(_download)
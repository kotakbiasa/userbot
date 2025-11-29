import re
import datetime
import math
import os
import httpx
import asyncio
from pathlib import Path

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtbyte
from selfbot.utils.youtube_api import YouTube, shell


pattern = re.compile(r"^song(?:\s+(-d|--doc|-v|--voice))?\s+(.+)")
youtube = YouTube()


class Song(Module):
    name = "Song"
    cmds = "song (-d|--doc|-v|--voice)? {query}"
    desc = {
        "query": "A YouTube video link or search query.",
        "-d, --doc": "Send as a document file.",
        "-v, --voice": "Send as a voice message.",
        "e.g.": "song https://youtu.be/es4WLcvl7Fc",
    }

    async def _get_waveform(self, audio_path: str) -> bytes | None:
        """
        Generates waveform data for a voice message from an audio file using ffmpeg.
        The waveform consists of 100 samples of 5-bit amplitude values.
        """
        try:
            # Perintah untuk mengubah audio menjadi data mentah (raw) 8-bit mono
            command = (
                f"ffmpeg -i \"{audio_path}\" -f u8 -ac 1 -ar 8000 -"
            )
            stdout, _ = await shell(command)
            
            # Konversi output biner menjadi byte
            raw_waveform = bytes(stdout, "latin-1")

            if not raw_waveform:
                return None

            # Ambil sampel dari data mentah untuk membuat waveform
            num_samples = 100
            step = len(raw_waveform) // num_samples
            if step == 0:
                return None

            # Ambil sampel dan normalisasi ke rentang 0-31
            sampled_waveform = [raw_waveform[i] for i in range(0, len(raw_waveform), step)]
            normalized_waveform = [int((sample / 255) * 31) for sample in sampled_waveform]
            return bytes(normalized_waveform[:num_samples])
        except Exception as e:
            self.logger.error(f"Gagal membuat waveform: {e}")
            return None

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Downloads a song from a YouTube link."""
        await event.edit_text("<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)
        match = pattern.match(event.text)
        if not match:
            await event.edit_text("<b>Usage:</b> <code>song &lt;youtube_link | search_query&gt;</code>")
            return

        flag, query = match.groups()
        api_key = self.client.config.get("FERDEV_API_KEY", "key_iOPE5w")

        if not youtube.valid(query):
            await event.edit_text(f"<code>Searching for '{query}'...</code>")
            track = await youtube.search(query, m_id=event.id)
            if not track:
                await event.edit_text(f"<code>No results found for '{query}'.</code>")
                return
            yt_link = track.url
        else:
            yt_link = query

        await event.edit_text("<code>Fetching song from API...</code>")

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                api_url = f"https://api.ferdev.my.id/downloader/ytmp3?link={yt_link}&apikey={api_key}"
                resp = await client.get(api_url)
                resp.raise_for_status()
                data = resp.json()

                if not data.get("success") or not data.get("data"):
                    raise Exception(f"API returned an error: {data.get('message', 'Unknown error')}")

                song_data = data["data"]
                title = song_data.get("title", "Untitled")
                duration = int(song_data.get("duration", 0))
                thumb_url = song_data.get("thumbnail")
                dlink = song_data.get("dlink")
                size = song_data.get("size")

                if not dlink:
                    raise Exception("API did not provide a download link.")

                await event.edit_text(f"<code>Downloading: {title}</code>")

                # Download audio and thumbnail concurrently
                audio_content_task = client.get(dlink, timeout=300)
                thumb_content_task = client.get(thumb_url) if thumb_url else asyncio.sleep(0)
                audio_resp, thumb_resp = await asyncio.gather(audio_content_task, thumb_content_task)
                audio_resp.raise_for_status()

                # Save files
                download_dir = Path("downloads")
                download_dir.mkdir(exist_ok=True)
                audio_file = download_dir / f"{title[:50]}.mp3"
                thumb_file = download_dir / f"thumb_{event.id}.jpg"

                with open(audio_file, "wb") as f:
                    f.write(audio_resp.content)
                
                if thumb_url and thumb_resp.status_code == 200:
                    with open(thumb_file, "wb") as f:
                        f.write(thumb_resp.content)
                else:
                    thumb_file = None

            duration_str = f"{duration // 60:02d}:{duration % 60:02d}"
            caption_parts = [
                f"<b>Title:</b> {title}",
                f"<b>Duration:</b> {duration_str}",
                f"<b>Size:</b> {fmtbyte(size)}"
            ]
            caption = "\n".join(caption_parts) + f"\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"

            if flag in ["-d", "--doc"]:
                await event.reply_document(document=audio_file, caption=caption, thumb=thumb_file)
            elif flag in ["-v", "--voice"]:
                waveform = await self._get_waveform(str(audio_file))
                await event.reply_voice(
                    voice=audio_file, 
                    caption=caption, 
                    duration=duration, 
                    waveform=waveform)
            else:
                await event.reply_audio(audio=audio_file, caption=caption, title=title, duration=duration, thumb=thumb_file)

            await event.delete()

        except Exception as e:
            await event.edit_text(f"<b>An error occurred:</b> <code>{e}</code>")
        finally:
            # Cleanup
            if 'audio_file' in locals() and os.path.exists(audio_file): os.remove(audio_file)
            if 'thumb_file' in locals() and thumb_file and os.path.exists(thumb_file): os.remove(thumb_file)
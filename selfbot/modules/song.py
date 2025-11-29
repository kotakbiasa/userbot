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
        Generates waveform data from actual audio file using ffmpeg.
        The waveform consists of 100 samples of 5-bit amplitude values.
        """
        try:
            # Extract raw audio data dari file MP3
            command = (
                f"ffmpeg -i \"{audio_path}\" -f u8 -ac 1 -ar 8000 -"
            )
            stdout, _ = await shell(command)
            
            # Convert output ke bytes
            if isinstance(stdout, bytes):
                raw_waveform = stdout
            else:
                raw_waveform = bytes(stdout, "latin-1") if stdout else b""

            if not raw_waveform or len(raw_waveform) < 100:
                return None

            # Ambil sampel setiap N bytes untuk mendapat 100 sampel
            num_samples = 100
            step = len(raw_waveform) // num_samples
            if step == 0:
                step = 1

            # Sample dan normalisasi ke range 0-31
            sampled = []
            for i in range(num_samples):
                idx = min(i * step, len(raw_waveform) - 1)
                # Normalisasi dari 0-255 ke 0-31
                sample_val = int((raw_waveform[idx] / 255) * 31)
                sampled.append(max(0, min(31, sample_val)))

            return bytes(sampled)
        except Exception as e:
            self.logger.error(f"Failed to generate waveform: {e}")
            return None
    
    async def _send_voice(self, event: Message, audio_file: Path, caption: str, duration: int) -> None:
        """Helper method to send voice with waveform."""
        waveform = await self._get_waveform(str(audio_file))
        await event.reply_voice(
            voice=audio_file,
            caption=caption,
            duration=duration,
            waveform=waveform
        )

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

        audio_file = None
        thumb_file = None

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
                size = song_data.get("size", 0)

                if not dlink:
                    raise Exception("API did not provide a download link.")

                await event.edit_text(f"<code>Downloading: {title}</code>")

                # Create download directory
                download_dir = Path("downloads")
                download_dir.mkdir(exist_ok=True)
                
                # Sanitize filename
                safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
                audio_file = download_dir / f"{safe_title}.mp3"
                thumb_file = download_dir / f"thumb_{event.id}.jpg"

                # Download audio with progress tracking
                try:
                    async with client.stream("GET", dlink, timeout=300) as audio_stream:
                        audio_stream.raise_for_status()
                        audio_content = b""
                        async for chunk in audio_stream.aiter_bytes(chunk_size=8192):
                            audio_content += chunk
                        
                        if not audio_content:
                            raise Exception("Downloaded audio is empty")
                        
                        with open(audio_file, "wb") as f:
                            f.write(audio_content)
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    raise Exception(f"Failed to download audio: {str(e)}")

                # Download thumbnail if available
                if thumb_url:
                    try:
                        thumb_resp = await client.get(thumb_url, timeout=30)
                        thumb_resp.raise_for_status()
                        if thumb_resp.content:
                            with open(thumb_file, "wb") as f:
                                f.write(thumb_resp.content)
                        else:
                            thumb_file = None
                    except (httpx.RequestError, httpx.HTTPStatusError):
                        self.logger.warning(f"Failed to download thumbnail for {title}")
                        thumb_file = None
                else:
                    thumb_file = None

                # Validate downloaded file
                if not audio_file.exists() or audio_file.stat().st_size == 0:
                    raise Exception("Audio file download failed or is empty")

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
                await self._send_voice(event, audio_file, caption, duration)
            else:
                await event.reply_audio(audio=audio_file, caption=caption, title=title, duration=duration, thumb=thumb_file)

            await event.delete()

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Song download error: {error_msg}")
            await event.edit_text(f"<b>An error occurred:</b>\n<code>{error_msg[:200]}</code>")
        finally:
            # Cleanup with error handling
            for file_path in [audio_file, thumb_file]:
                if file_path:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except OSError as e:
                        self.logger.warning(f"Failed to cleanup {file_path}: {e}")
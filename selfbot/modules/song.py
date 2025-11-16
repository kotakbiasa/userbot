import re
import datetime
import os
import validators
import httpx

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec
from selfbot.utils.youtube_api import YouTubeAPI

def format_bytes(size):
    """Converts bytes to a human-readable format."""
    if size is None:
        return "N/A"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power and n < len(power_labels) -1 :
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"


pattern = re.compile(r"^song(?:\s+(-d|--doc|-v|--voice))?\s+(.+)")
youtube = YouTubeAPI()


class Song(Module):
    name = "Song"
    cmds = "song (-d|--doc|-v|--voice)? {query}"
    desc = {
        "query": "A YouTube video link or search query.",
        "-d, --doc": "Send as a document file.",
        "-v, --voice": "Send as a voice message.",
        "e.g.": "song https://youtu.be/es4WLcvl7Fc",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Downloads a song from a YouTube link."""
        now = datetime.datetime.now(datetime.UTC)
        match = pattern.match(event.text)
        if not match:
            await event.edit_text("<b>Usage:</b> <code>.song &lt;youtube_link | search_query&gt;</code>")
            return

        flag, query = match.groups()

        if not validators.url(query):
            await event.edit_text(f"<code>Searching for '{query}'...</code>")
            results = await youtube.search(query, limit=1)
            if not results:
                await event.edit_text(f"<code>No results found for '{query}'.</code>")
                return
            yt_link = results[0]["link"]
        else:
            yt_link = query

        await event.edit_text("<code>Fetching song details...</code>")

        try:
            details = await youtube.details(yt_link)
            if not details:
                await event.edit_text("<code>Could not fetch song details.</code>")
                return

            title = details["title"]
            duration = details["duration_sec"]
            thumb_url = details["thumbnail"]

            await event.edit_text(f"<code>Downloading: {title}</code>")
            
            # Download audio using yt-dlp
            audio_file = await youtube.download(yt_link)
            file_name = os.path.basename(audio_file)
            
            size = os.path.getsize(audio_file) if os.path.exists(audio_file) else 0

            thumb_path = None
            if thumb_url:
                try:
                    async with httpx.AsyncClient() as client:
                        thumb_res = await client.get(thumb_url)
                        thumb_res.raise_for_status()
                        thumb_path = f"thumb_{event.id}.jpg"
                        with open(thumb_path, "wb") as f:
                            f.write(thumb_res.content)
                except Exception:
                    thumb_path = None

            # Mengambil metadata durasi
            duration_str = details.get("duration_string", f"{duration // 60:02d}:{duration % 60:02d}")

            # Membangun caption baru
            caption_parts = [
                f"<b>Title:</b> {title}",
                f"<b>Duration:</b> {duration_str}"
            ]
            caption = "\n".join(caption_parts) + f"\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"
            
            if flag in ["-d", "--doc"]:
                await event.reply_document(
                    document=audio_file,
                    caption=caption,
                    thumb=thumb_path,
                    file_name=file_name
                )
            elif flag in ["-v", "--voice"]:
                await event.reply_voice(voice=audio_file, caption=caption, duration=duration)
            else:
                await event.reply_audio(audio=audio_file, caption=caption, title=title, duration=duration, thumb=thumb_path)

            await event.delete()

            # Cleanup
            if os.path.exists(audio_file): os.remove(audio_file)
            if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)

        except Exception as e:
            await event.edit_text(f"<b>An error occurred:</b> <code>{e}</code>")
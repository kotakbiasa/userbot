import asyncio
import os
import shutil
import time
from io import BytesIO
from pathlib import Path

from PIL import Image
from pyrogram import filters
from pyrogram.enums import MessageMediaType
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import shell


class Unsticker(Module):
    name = "Unsticker"

    cmds = "<Reply to Sticker> unsticker"
    desc = {
        "Info": "Mengekstrak sticker menjadi file gambar/video.",
        "Static Sticker": "Diekstrak menjadi PNG.",
        "Animated Sticker": "Diekstrak menjadi GIF.",
        "Video Sticker": "Diekstrak menjadi MP4.",
    }

    @listener.handler(filters.regex(r"^unsticker$") & listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        """Handler untuk perintah unsticker."""
        response = await event.edit_text("<code>Mengekstrak sticker...</code>")
        replied_msg = event.reply_to_message

        if not replied_msg or replied_msg.media != MessageMediaType.STICKER:
            await response.edit("<b>Reply ke sticker untuk mengekstraknya!</b>")
            return

        sticker = replied_msg.sticker
        
        try:
            if sticker.is_animated:
                # Lottie animated sticker (.tgs)
                await self._extract_animated(replied_msg, response)
            elif sticker.is_video:
                # Video sticker (.webm)
                await self._extract_video(replied_msg, response)
            else:
                # Static sticker (.webp)
                await self._extract_static(replied_msg, response)
        except Exception as e:
            await response.edit(f"<b>Error:</b>\n<code>{e}</code>")

    async def _extract_static(self, message: Message, response: Message) -> None:
        """Mengekstrak static sticker (.webp) menjadi PNG."""
        # Download sticker ke memory
        sticker_data = await message.download(in_memory=True)
        sticker_data.seek(0)

        # Convert WebP ke PNG menggunakan Pillow
        image = await asyncio.to_thread(Image.open, sticker_data)
        output = BytesIO()
        output.name = "sticker.png"
        await asyncio.to_thread(image.save, output, format="PNG")
        output.seek(0)

        # Kirim sebagai dokumen
        await self.client.app.send_document(
            chat_id=message.chat.id,
            document=output,
            reply_to_message_id=message.id,
            caption="<b>📷 Sticker diekstrak ke PNG</b>",
        )
        await response.delete()

    async def _extract_video(self, message: Message, response: Message) -> None:
        """Mengekstrak video sticker (.webm) menjadi MP4."""
        download_path = Path("downloads") / f"unsticker_{int(time.time())}"
        download_path.mkdir(parents=True, exist_ok=True)

        webm_file = download_path / "sticker.webm"
        mp4_file = download_path / "sticker.mp4"

        try:
            # Download sticker
            await message.download(str(webm_file))

            # Convert WebM ke MP4 menggunakan ffmpeg
            cmd = (
                f"ffmpeg -hide_banner -loglevel error -i '{webm_file}' "
                f"-c:v libx264 -pix_fmt yuv420p -movflags +faststart "
                f"'{mp4_file}'"
            )
            await shell(cmd)

            # Kirim video
            await self.client.app.send_video(
                chat_id=message.chat.id,
                video=str(mp4_file),
                reply_to_message_id=message.id,
                caption="<b>🎬 Sticker video diekstrak ke MP4</b>",
            )
            await response.delete()
        finally:
            # Cleanup
            shutil.rmtree(download_path, ignore_errors=True)

    async def _extract_animated(self, message: Message, response: Message) -> None:
        """Mengekstrak animated sticker (.tgs) menjadi GIF."""
        download_path = Path("downloads") / f"unsticker_{int(time.time())}"
        download_path.mkdir(parents=True, exist_ok=True)

        tgs_file = download_path / "sticker.tgs"
        gif_file = download_path / "sticker.gif"

        try:
            # Download sticker
            await message.download(str(tgs_file))

            # Convert TGS ke GIF menggunakan lottie library
            # TGS adalah format Lottie yang dikompresi dengan gzip
            try:
                from lottie.importers.core import import_tgs
                from lottie.exporters.gif import export_gif
            except ImportError:
                await response.edit(
                    "<b>Error:</b> Library <code>lottie</code> tidak terinstall.\n"
                    "Install dengan: <code>pip install lottie[gif]</code>"
                )
                return

            # Load TGS dan export ke GIF
            animation = await asyncio.to_thread(import_tgs, str(tgs_file))
            await asyncio.to_thread(export_gif, animation, str(gif_file), skip_frames=2)

            # Kirim GIF sebagai animation
            await self.client.app.send_animation(
                chat_id=message.chat.id,
                animation=str(gif_file),
                reply_to_message_id=message.id,
                caption="<b>✨ Sticker animasi diekstrak ke GIF</b>",
            )
            await response.delete()
        finally:
            # Cleanup
            shutil.rmtree(download_path, ignore_errors=True)

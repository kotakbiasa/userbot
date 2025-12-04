import asyncio
import os
import re
from pathlib import Path

from PIL import Image
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module


class Converter(Module):
    name = "Converter"
    cmds = [
        "toimg",
        "tosticker",
        "togif",
        "toaudio",
        "tovoice",
        "tovnote",
        "topdf",
    ]
    desc = {
        "toimg": "Convert replied media to an image.",
        "tosticker": "Convert replied media to a sticker.",
        "togif": "Convert replied video/sticker to a GIF.",
        "toaudio": "Extract audio from a replied video.",
        "tovoice": "Convert replied audio/video to a voice message.",
        "tovnote": "Convert replied video/gif to a video note.",
        "topdf": "Convert replied image(s) to a PDF document.",
    }

    async def _download_and_edit(self, event: Message, text: str = "...") -> str | None:
        """Helper to download media from a replied message and edit the status."""
        if not event.reply_to_message or not event.reply_to_message.media:
            await event.edit_text("❌ Reply to a media to convert.")
            return None
        await event.edit_text(f"<code>{text}</code>")
        return await event.reply_to_message.download()

    @listener.handler(filters.regex(r"^toimg") & listener.fltrep, 1)
    async def to_img(self, event: Message):
        if file_path := await self._download_and_edit(event, "Converting to image..."):
            await event.client.send_photo(event.chat.id, photo=file_path)
            await event.delete()
            os.remove(file_path)

    @listener.handler(filters.regex(r"^tosticker") & listener.fltrep, 1)
    async def to_sticker(self, event: Message):
        if file_path := await self._download_and_edit(event, "Converting to sticker..."):
            await event.client.send_sticker(event.chat.id, sticker=file_path)
            await event.delete()
            os.remove(file_path)

    @listener.handler(filters.regex(r"^togif") & listener.fltrep, 1)
    async def to_gif(self, event: Message):
        if file_path := await self._download_and_edit(event, "Converting to GIF..."):
            await event.client.send_animation(event.chat.id, animation=file_path)
            await event.delete()
            os.remove(file_path)

    @listener.handler(filters.regex(r"^toaudio") & listener.fltrep, 1)
    async def to_audio(self, event: Message):
        if file_path := await self._download_and_edit(event, "Converting to audio..."):
            await event.client.send_audio(event.chat.id, audio=file_path)
            await event.delete()
            os.remove(file_path)

    @listener.handler(filters.regex(r"^tovoice") & listener.fltrep, 1)
    async def to_voice(self, event: Message):
        if file_path := await self._download_and_edit(event, "Converting to voice message..."):
            await event.client.send_voice(event.chat.id, voice=file_path)
            await event.delete()
            os.remove(file_path)

    @listener.handler(filters.regex(r"^tovnote") & listener.fltrep, 1)
    async def to_vnote(self, event: Message):
        if file_path := await self._download_and_edit(event, "Converting to video note..."):
            await event.client.send_video_note(event.chat.id, video_note=file_path)
            await event.delete()
            os.remove(file_path)

    @listener.handler(filters.regex(r"^topdf") & listener.fltrep, 1)
    async def to_pdf(self, event: Message):
        if not event.reply_to_message:
            await event.edit_text("❌ Reply to an image or a media group.")
            return

        await event.edit_text("<code>Processing images...</code>")
        
        replied = event.reply_to_message
        media_group = await event.client.get_media_group(event.chat.id, replied.id) if replied.media_group_id else [replied]

        image_paths = []
        for msg in media_group:
            if msg.photo or (msg.document and "image" in msg.document.mime_type):
                if path := await msg.download():
                    image_paths.append(path)

        if not image_paths:
            await event.edit_text("❌ No valid images found to convert.")
            return

        await event.edit_text(f"<code>Converting {len(image_paths)} image(s) to PDF...</code>")
        images = [Image.open(p).convert("RGB") for p in image_paths]
        pdf_path = Path("downloads") / f"converted_{event.id}.pdf"
        images[0].save(pdf_path, save_all=True, append_images=images[1:])
        
        await event.reply_document(document=str(pdf_path), caption=f"📄 PDF from {len(images)} image(s)")
        await event.delete()

        # Cleanup
        os.remove(pdf_path)
        for p in image_paths:
            os.remove(p)
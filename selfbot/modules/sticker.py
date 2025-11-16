import asyncio
import io
import os
import datetime
import random
import re
import shutil
import time
from io import BytesIO
from pathlib import Path

from pyrogram.enums import MessageMediaType
from pyrogram.errors import StickersetInvalid
from pyrogram.raw import functions
from pyrogram.raw import types as raw_types
from pyrogram.raw.base.messages import StickerSet
from pyrogram.types import LinkPreviewOptions, Message, User
from pyrogram.utils import FileId
from PIL import Image
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import shell, fmtsec

EMOJIS = ("☕", "🤡", "🙂", "🤔", "🔪", "😂", "💀")

pattern = re.compile(r"^kang(\s-f)?$")


class Sticker(Module):
    name = "Sticker"

    cmds = "<Reply to Media> kang (-f)?"
    desc = {
        "Info": "Saves a sticker/image/gif/video to your sticker pack.",
        "-f": "Fast-forwards the video to fit the 3-second duration.",
        "e.g.": "<Reply to Video> kang -f",
    }

    @listener.handler(filters.regex(pattern) & listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        """Handler utama untuk perintah kang."""
        replied_msg = event.reply_to_message
        media_func = self.MEDIA_TYPE_MAP.get(replied_msg.media)

        if not media_func:
            await event.edit_text("<code>Unsupported media...</code>")
            return

        response = await event.edit_text("<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        try:
            file_id, emoji, temp_msg = await media_func(self, message=replied_msg, ff="-f" in event.text)
            stickers: StickerSet = await self._kang_sticker(event._client, file_id, emoji, user=event.from_user)
            url = f"https://t.me/addstickers/{stickers.set.short_name}"
            await asyncio.gather(
                response.edit(
                    f"<b><blockquote>{fmtsec(now)}</blockquote></b>",
                    link_preview_options=LinkPreviewOptions(
                        url=url, show_above_text=True
                    ),
                ),
                temp_msg.delete() if temp_msg else asyncio.sleep(0) # Hapus pesan sementara
            )
        except Exception as e:
            await response.edit(f"<b>Error:</b>\n<code>{e}</code>")

    async def _save_sticker(self, file: Path | BytesIO) -> Message:
        """Uploads a file to saved messages to get a file_id."""
        sent_file = await self.client.app.send_document(chat_id="me", document=file)
        if isinstance(file, Path) and file.is_file():
            shutil.rmtree(file.parent, ignore_errors=True)
        return sent_file

    def _resize_photo(self, input_file: BytesIO) -> BytesIO:
        """Resizes a photo to sticker dimensions."""
        image = Image.open(input_file)
        maxsize = 512
        scale = maxsize / max(image.width, image.height)
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
        resized_photo = BytesIO()
        resized_photo.name = "sticker.png"
        image.save(resized_photo, format="PNG")
        return resized_photo

    async def _photo_kang(self, message: Message, **_) -> tuple[str, None, Message]:
        file = await message.download(in_memory=True)
        file.seek(0)
        resized_file = await asyncio.to_thread(self._resize_photo, file)
        temp_msg = await self._save_sticker(resized_file)
        return temp_msg.document.file_id, None, temp_msg

    async def _video_kang(self, message: Message, ff=False) -> tuple[str, None, Message]:
        video = message.video or message.animation or message.document
        if video.file_size > 5242880:
            raise MemoryError("File size exceeds 5MB.")

        download_path = Path("downloads") / str(time.time())
        input_file = download_path / "input.mp4"
        output_file = download_path / "sticker.webm"
        download_path.mkdir(parents=True, exist_ok=True)

        await message.download(str(input_file))
        duration = getattr(video, "duration", 3)

        await self._resize_video(input_file=input_file, output_file=output_file, duration=duration, ff=ff)
        temp_msg = await self._save_sticker(output_file)
        return temp_msg.document.file_id, None, temp_msg

    async def _resize_video(self, input_file: Path | str, output_file: Path | str, duration: int, ff: bool = False):
        cmd = f"ffmpeg -hide_banner -loglevel error -i '{input_file}' -vf "
        if ff:
            cmd += '"scale=w=512:h=512:force_original_aspect_ratio=decrease,setpts=0.3*PTS" '
            cmd += "-ss 0 -t 3 -r 30 -loop 0 -an -c:v libvpx-vp9 -b:v 256k -fs 256k "
        else:
            cmd += '"scale=w=512:h=512:force_original_aspect_ratio=decrease" '
            cmd += f"-ss 0 -t {min(duration, 3)} -r 30 -an -c:v libvpx-vp9 -b:v 256k -fs 256k "
        await shell(f"{cmd}'{output_file}'")

    async def _document_kang(self, message: Message, ff: bool = False) -> tuple[str, None, Message]:
        file_name = getattr(message.document, 'file_name', '')
        if file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            return await self._photo_kang(message)
        elif file_name.lower().endswith(('.mp4', '.mov', '.webm', '.gif')):
            return await self._video_kang(message=message, ff=ff)
        raise TypeError("Unsupported document type.")

    async def _sticker_kang(self, message: Message, **_) -> tuple[str, str, Message | None]:
        sticker = message.sticker
        if sticker.is_video:
            return await self._video_kang(message)
        if sticker.is_animated:
            raise TypeError("Lottie animated stickers (.tgs) are not supported.")
        return sticker.file_id, sticker.emoji, None

    async def _get_sticker_set(self, client, user: User) -> tuple[str, str, bool, StickerSet | None]:
        count = 0
        create_new = False
        suffix = f"_by_{self.client.app.me.username}"

        while True:
            shortname = f"kang_{user.id}_{count}{suffix}"
            try:
                sticker_set_raw: BaseStickerSet = await client.invoke(
                    functions.messages.GetStickerSet(
                        stickerset=raw_types.InputStickerSetShortName(short_name=shortname), hash=0
                    )
                )
                sticker_set = sticker_set_raw.set
                if sticker_set.count < 120:
                    break
                count += 1
            except StickersetInvalid:
                create_new = True
                sticker_set: StickerSet | None = None
                break

        pack_title = f"{user.first_name}'s Kang Pack Vol. {count + 1}"
        return shortname, pack_title, create_new, sticker_set

    async def _kang_sticker(self, client, media_file_id: str, emoji: str = None, user: User = None) -> StickerSet:
        shortname, pack_title, create_new, sticker_set = await self._get_sticker_set(client, user)
        file_id = FileId.decode(media_file_id)

        document = raw_types.InputDocument(
            id=file_id.media_id,
            access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
        )

        set_item = raw_types.InputStickerSetItem(document=document, emoji=emoji or random.choice(EMOJIS))

        if create_new:
            query = functions.stickers.CreateStickerSet(
                user_id=await client.resolve_peer(peer_id=user.id),
                short_name=shortname,
                title=pack_title,
                stickers=[set_item],
            )
        else:
            query = functions.stickers.AddStickerToSet(
                stickerset=raw_types.InputStickerSetID(id=sticker_set.id, access_hash=sticker_set.access_hash),
                sticker=set_item,
            )
        return await client.invoke(query)

    MEDIA_TYPE_MAP = {
        MessageMediaType.PHOTO: _photo_kang,
        MessageMediaType.VIDEO: _video_kang,
        MessageMediaType.ANIMATION: _video_kang,
        MessageMediaType.DOCUMENT: _document_kang,
        MessageMediaType.STICKER: _sticker_kang,
    }
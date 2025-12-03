import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

pattern = re.compile(r"^id$")


class Id(Module):
    name = "ID"
    cmds = "id"
    desc = {
        "Info": "Get the ID of the current chat, replied user/message, or sticker.",
        "e.g.": "<Reply> id",
    }

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        """Fetches and displays various IDs based on context."""
        now = datetime.datetime.now(datetime.UTC)

        # Basic chat info
        chat = event.chat
        data = {
            "Chat ID": getattr(chat, "id", "N/A"),
            "Chat Type": getattr(chat, "type", "N/A").name if getattr(chat, "type", None) else "N/A",
            "Chat Title": getattr(chat, "title", None) or getattr(chat, "username", None) or "",
        }

        replied = event.reply_to_message
        if replied:
            data["Replied Msg ID"] = replied.id
            # Attempt to build a permalink if possible
            try:
                if getattr(chat, "username", None):
                    data["Permalink"] = f"https://t.me/{chat.username}/{replied.id}"
                else:
                    # for supergroups without username
                    if str(chat.id).startswith("-100"):
                        cid = str(chat.id).replace("-100", "")
                        data["Permalink"] = f"https://t.me/c/{cid}/{replied.id}"
            except Exception:
                pass

            # Replied user info (may be None for anonymous/admin)
            if replied.from_user:
                data["User ID"] = replied.from_user.id
                if getattr(replied.from_user, "username", None):
                    data["User"] = f"@{replied.from_user.username}"
                else:
                    data["User"] = getattr(replied.from_user, "first_name", "") or ""
            else:
                # Could be anonymous admin or channel post
                data["User"] = "Anonymous / Channel Post"
                data["User ID"] = "N/A"

            # Forwarded info (various forward fields)
            fwd_from_user = getattr(replied, "forward_from", None)
            fwd_from_chat = getattr(replied, "forward_from_chat", None)
            fwd_sender_name = getattr(replied, "forward_sender_name", None)
            if fwd_from_user:
                data["Fwd User ID"] = getattr(fwd_from_user, "id", "N/A")
            if fwd_from_chat:
                data["Fwd Chat ID"] = getattr(fwd_from_chat, "id", "N/A")
            if fwd_sender_name:
                data["Fwd Sender Name"] = fwd_sender_name

            # Media/file specific info
            # Helper to add file fields
            def add_file_info(prefix: str, obj):
                if not obj:
                    return
                fid = getattr(obj, "file_id", None)
                funq = getattr(obj, "file_unique_id", None)
                ftype = getattr(obj, "mime_type", None) or getattr(obj, "file_name", None) or ""
                if fid:
                    data[f"{prefix} File ID"] = fid
                if funq:
                    data[f"{prefix} Unique ID"] = funq
                if ftype:
                    data[f"{prefix} Type"] = ftype

            # Sticker
            if replied.sticker:
                data["Sticker ID"] = replied.sticker.file_id
                data["Sticker Unique ID"] = getattr(replied.sticker, "file_unique_id", "")
                data["Sticker Pack"] = getattr(replied.sticker, "set_name", "")
            # Photo (list of sizes) -> get largest
            if replied.photo:
                # photos is list-like; pick last item
                photo_obj = replied.photo[-1] if isinstance(replied.photo, (list, tuple)) else replied.photo
                add_file_info("Photo", photo_obj)
            # Video
            if replied.video:
                add_file_info("Video", replied.video)
            # Animation (GIF)
            if replied.animation:
                add_file_info("Animation", replied.animation)
            # Voice
            if replied.voice:
                add_file_info("Voice", replied.voice)
            # Audio / Music
            if replied.audio:
                add_file_info("Audio", replied.audio)
            # Document (includes stickers sometimes)
            if replied.document:
                add_file_info("Document", replied.document)

        else:
            # Not replied: show sender (you) info
            sender = event.from_user
            if sender:
                data["Your ID"] = sender.id
                if getattr(sender, "username", None):
                    data["Your Username"] = f"@{sender.username}"
                data["Your Name"] = getattr(sender, "first_name", "") or ""
            else:
                data["Your ID"] = "N/A"

        # Build output without monospace for keys (left side)
        lines = []
        for k, v in data.items():
            # safe escape and avoid using <code> for labels or values
            key = html.escape(str(k))
            val = html.escape(str(v)) if v is not None else ""
            lines.append(f"<b>{key}:</b> {val}")

        output = "\n".join(lines) + f"\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"
        # Jika perintah dipanggil sambil membalas pesan, kirim hasil sebagai reply ke pesan tersebut
        if replied:
            try:
                await event.reply_text(output, reply_to_message_id=replied.id, disable_web_page_preview=True)
                # Hapus pesan perintah agar tidak berantakan
                try:
                    await event.delete()
                except Exception:
                    pass
                return
            except Exception as e:
                # Jika gagal mengirim sebagai reply, fallback ke edit pesan perintah
                self.logger.debug(f"Failed to reply with IDs: {e}")

        # Default: edit pesan perintah
        await event.edit_text(output, disable_web_page_preview=True)
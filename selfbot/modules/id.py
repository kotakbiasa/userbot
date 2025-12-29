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

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Fetches and displays various IDs based on context."""
        now = datetime.datetime.now(datetime.UTC)

        # Basic chat info
        chat = event.chat
        data = {
            "Chat ID": getattr(chat, "id", "N/A"),
            "Chat Type": getattr(chat, "type", "N/A").name.title() if getattr(chat, "type", None) else "N/A",
            "Chat Title": getattr(chat, "title", None) or getattr(chat, "username", None) or "",
        }

        replied = event.reply_to_message
        if replied:
            data["Replied Msg ID"] = replied.id
            # Attempt to build a permalink if possible
            if replied.link:
                data["Permalink"] = replied.link

            # Replied user info (may be None for anonymous/admin)
            if replied.from_user:
                data["User ID"] = replied.from_user.id
                if getattr(replied.from_user, "username", None):
                    data["User"] = replied.from_user.mention
                else:
                    data["User"] = replied.from_user.mention(style="html")
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

            if replied.media:
                media_obj = getattr(replied, replied.media.value)
                media_type_name = replied.media.name.title().replace("_", " ")
                
                if file_id := getattr(media_obj, "file_id", None):
                    data[f"{media_type_name} File ID"] = f"<code>{file_id}</code>"
                if file_unique_id := getattr(media_obj, "file_unique_id", None):
                    data[f"{media_type_name} Unique ID"] = f"<code>{file_unique_id}</code>"
                if mime_type := getattr(media_obj, "mime_type", None):
                    data[f"{media_type_name} MIME"] = mime_type
                
                # Specific for stickers
                if replied.sticker and (set_name := getattr(replied.sticker, "set_name", None)):
                    data["Sticker Pack"] = set_name

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
        output = ""
        for k, v in data.items():
            if v: # Only add if value is not empty
                key = html.escape(str(k))
                # Value might already contain <code> tags, so don't escape it again
                val = str(v) if v is not None else ""
                lines.append(f"<b>{key}:</b> {val}")

        if lines:
            output = "\n".join(lines)
        
        output += f"\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"

        # Default: edit pesan perintah
        await event.edit_text(output, disable_web_page_preview=True)
import asyncio
import html
import re

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

try:
    from pytgcalls.exceptions import NoActiveGroupCall, UserAlreadyParticipant
except ImportError:
    # These will be None if pytgcalls is not installed.
    NoActiveGroupCall = UserAlreadyParticipant = None

# Pola Regex untuk perintah vcall
pattern = re.compile(r"^\.?(join|leave)\s*$")


class VCall(Module):
    name = "VCall"
    cmds = "join | leave"
    desc = {
        "Info": "Manages voice calls using an assistant account.",
        "join": "Commands the assistant to join the current group's voice chat.",
        "leave": "Commands the assistant to leave the current voice chat.",
        "e.g.": "join",
    }

    async def on_starting(self):
        """Inisialisasi saat startup."""
        # Pastikan klien asisten telah diinisialisasi di core selfbot
        if not self.client.assistant_calls or not UserAlreadyParticipant:
            self.logger.warning("Assistant client not configured or pytgcalls not installed. Module will be unloaded.")
            self.client.unload(self)
            return

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_vcall_command(self, event: Message) -> None:
        """Menangani perintah join/leave vcall."""
        command = (event.matches[0].group(1) or "").lower()

        if event.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await self._edit_and_delete(event, "<code>This command only works in groups.</code>")
            return

        if command == "join":
            await self._join_or_leave_call(event, "join")
        elif command == "leave":
            await self._join_or_leave_call(event, "leave")

    async def _join_or_leave_call(self, event: Message, action: str):
        """Logika terpusat untuk bergabung atau meninggalkan panggilan suara."""
        is_in_call = any(call.chat_id == event.chat.id for call in self.client.assistant_calls.calls)

        if action == "join":
            if is_in_call:
                await self._edit_and_delete(event, "<code>Assistant is already in this voice call.</code>")
                return
            await event.edit_text("<code>Assistant is joining the voice call...</code>")
            try:
                await self.client.assistant_calls.join_group_call(event.chat.id)
                await event.edit_text("<b>Assistant has joined the voice call.</b>")
            except NoActiveGroupCall:
                await self._edit_and_delete(event, "<code>There is no active voice call in this group.</code>")
            except UserAlreadyParticipant:
                await self._edit_and_delete(event, "<code>Assistant is already participating.</code>")
            except Exception as e:
                await event.edit_text(f"<b>Error joining call:</b>\n<code>{html.escape(str(e))}</code>")
        
        elif action == "leave":
            if not is_in_call:
                await self._edit_and_delete(event, "<code>Assistant is not in a voice call in this group.</code>")
                return
            await event.edit_text("<code>Assistant is leaving the voice call...</code>")
            try:
                await self.client.assistant_calls.leave_group_call(event.chat.id)
                await event.edit_text("<b>Assistant has left the voice call.</b>")
            except NoActiveGroupCall:
                await self._edit_and_delete(event, "<code>There is no active voice call to leave.</code>")
            except Exception as e:
                await event.edit_text(f"<b>Error leaving call:</b>\n<code>{html.escape(str(e))}</code>")

    async def _edit_and_delete(self, message: Message, text: str, duration: int = 8):
        """Mengedit pesan dan menghapusnya setelah durasi tertentu."""
        try:
            await message.edit_text(text)
            await asyncio.sleep(duration)
            await message.delete()
        except Exception:
            pass  # Abaikan jika pesan sudah terhapus atau terjadi error lain
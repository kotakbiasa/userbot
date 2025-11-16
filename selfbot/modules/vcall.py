import asyncio
import html
import re

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import NoActiveGroupCall, UserAlreadyParticipant
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

# Pola Regex untuk perintah vcall
pattern = re.compile(r"^(join|leave)$")


class VCall(Module):
    name = "VCall"
    cmds = "join | leave"
    desc = {
        "Info": "Manages voice calls using an assistant account.",
        "join": "Commands the assistant to join the current group's voice chat.",
        "leave": "Commands the assistant to leave the current voice chat.",
        "e.g.": "join",
    }

    async def on_init(self):
        """Inisialisasi saat startup."""
        self.is_vcall_active = False
        self.active_chat_id = None
        # Pastikan klien asisten telah diinisialisasi di core selfbot
        if not self.client.assistant:
            self.log.warning("Assistant client is not initialized. VCall module will be disabled.")
            # Menonaktifkan handler jika asisten tidak ada
            listener.remove_handler(self.on_vcall_command)

    @listener.handler(filters.regex(pattern), 1)
    async def on_vcall_command(self, event: Message) -> None:
        """Menangani perintah join/leave vcall."""
        match = pattern.match(event.text)
        command = match.group(1).lower()

        if event.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await self._edit_and_delete(event, "<code>This command only works in groups.</code>")
            return

        if command == "join":
            await self._join_call(event)
        elif command == "leave":
            await self._leave_call(event)

    async def _join_call(self, event: Message):
        """Logika untuk bergabung ke panggilan suara."""
        if self.is_vcall_active:
            await self._edit_and_delete(event, "<code>Assistant is already in a voice call.</code>")
            return

        await event.edit_text("<code>Assistant is joining the voice call...</code>")

        try:
            await self.client.assistant.join_group_call(event.chat.id)
            self.is_vcall_active = True
            self.active_chat_id = event.chat.id
            await event.edit_text("<b>Assistant has joined the voice call.</b>")

        except UserAlreadyParticipant:
            self.is_vcall_active = True
            self.active_chat_id = event.chat.id
            await self._edit_and_delete(event, "<code>Assistant is already in this voice call.</code>")
        except NoActiveGroupCall:
            await self._edit_and_delete(event, "<code>There is no active voice call in this group.</code>")
        except Exception as e:
            await event.edit_text(f"<b>Error joining call:</b>\n<code>{html.escape(str(e))}</code>")

    async def _leave_call(self, event: Message):
        """Logika untuk meninggalkan panggilan suara."""
        if not self.is_vcall_active:
            await self._edit_and_delete(event, "<code>Assistant is not in any voice call.</code>")
            return

        # Jika perintah leave dijalankan di chat yang berbeda dari call aktif
        if event.chat.id != self.active_chat_id:
            await self._edit_and_delete(event, "<code>Use the 'leave' command in the group where the call is active.</code>")
            return

        await event.edit_text("<code>Assistant is leaving the voice call...</code>")

        try:
            await self.client.assistant.leave_group_call(event.chat.id)
            self.is_vcall_active = False
            self.active_chat_id = None
            await event.edit_text("<b>Assistant has left the voice call.</b>")

        except NoActiveGroupCall:
            self.is_vcall_active = False
            self.active_chat_id = None
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
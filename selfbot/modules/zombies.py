import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import UserAdminInvalid
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

# Regex untuk mencocokkan 'zombies' dengan flag '-clean' opsional
pattern = re.compile(r"^zombies(?:\s+(-clean))?$")


class Zombies(Module):
    name = "Zombies"
    cmds = "zombies (-clean)?"
    desc = {
        "Info": "Finds or cleans up deleted accounts (zombies) in a group.",
        "-clean": "Kick all deleted accounts from the group.",
        "?": "Optional",
        "e.g.": "zombies -clean",
    }

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        """Mencari dan/atau membersihkan akun yang terhapus dari grup."""
        if event.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await event.edit_text("<code>This command can only be used in groups.</code>")
            return

        member = await event.chat.get_member(event.from_user.id)
        if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR] or not member.privileges.can_restrict_members:
            await event.edit_text("<code>You don't have permission to kick members.</code>")
            return

        match = pattern.match(event.text)
        clean_mode = bool(match.group(1))

        await event.edit_text("<code>Searching for deleted accounts...</code>")
        now = datetime.datetime.now(datetime.UTC)
        
        zombies_found = 0
        zombies_kicked = 0
        
        try:
            # Always use event.chat.id, as it refers to the main supergroup even in topics.
            async for member in event._client.get_chat_members(event.chat.id):
                if member.user.is_deleted:
                    zombies_found += 1
                    if clean_mode:
                        try:
                            await event.chat.ban_member(member.user.id)
                            zombies_kicked += 1
                            # Beri jeda untuk menghindari flood
                            await asyncio.sleep(0.5)
                        except UserAdminInvalid:
                            # Gagal mengeluarkan admin lain atau pemilik
                            pass

            if clean_mode:
                result_text = f"Cleanup Complete"
                result_data = {"Found": f"{zombies_found} accounts", "Kicked": f"{zombies_kicked} accounts"}
            else:
                result_text = f"Search Complete"
                result_data = {"Deleted Accounts": f"{zombies_found} accounts"}

            await event.edit_text(fmtstr(result_text, result_data, fmtsec(now)))

        except Exception as e:
            await event.edit_text(
                f"<b>Error:</b> An error occurred while processing members.\n<code>{html.escape(str(e))}</code>"
            )
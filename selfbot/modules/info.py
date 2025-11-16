import datetime
import html
import re

from pyrogram import enums, filters
from pyrogram.enums import ChatMemberStatus, ChatType, UserStatus
from pyrogram.errors import RPCError, UserIsBlocked
from pyrogram.types import LinkPreviewOptions, Message, User

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

pattern = re.compile(r"^info(.*)$", flags=re.DOTALL)


class Info(Module):
    name = "Info"
    cmds = "info {user_id|username}? (-f|-full)?"
    desc = {
        "user_id|username": "User ID or username of the target.",
        "?": "Optional. Reply to a message or get self info.",
        "-f|-full": "Get detailed information.",
        "e.g.": "info @username",
        "e.g. (full)": "info -f @username",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Get user information."""
        await event.edit_text("<code>Fetching user information...</code>")
        now = datetime.datetime.now(datetime.UTC)

        match = pattern.match(event.text)
        input_str = match.group(1).strip()

        args = input_str.split()
        is_full_mode = "-full" in args or "-f" in args
        target_identifier = input_str.replace("-full", "").replace("-f", "").strip()

        if not target_identifier:
            if event.reply_to_message and event.reply_to_message.from_user:
                target_identifier = event.reply_to_message.from_user.id
            else:
                target_identifier = event.from_user.id

        try:
            user = await event._client.get_users(target_identifier)
            if not isinstance(user, User):
                user = user[0] if isinstance(user, list) and user else None

            if not user:
                await event.edit_text(f"<code>User '{html.escape(str(target_identifier))}' not found.</code>")
                return

            caption, photo_id = await self._format_user_info(user, is_full_mode, event)
            caption += f"\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"

            if photo_id:
                photo = await event._client.download_media(photo_id, in_memory=True)
                await event.delete()
                await event.reply_photo(photo=photo, caption=caption)
            else:
                await event.edit_text(caption, link_preview_options=LinkPreviewOptions(is_disabled=True))

        except RPCError as e:
            await event.edit_text(f"<b>RPCError:</b> <code>{html.escape(str(e))}</code>")
        except Exception as e:
            await event.edit_text(f"<b>Error:</b> <code>{html.escape(str(e))}</code>")

    def _get_user_status(self, user: User) -> str:
        """Gets a formatted user status string."""
        if not user.status:
            return "N/A"
        
        status_map = {
            UserStatus.ONLINE: "Online",
            UserStatus.OFFLINE: user.last_online_date.strftime('%d %b %Y, %H:%M') if user.last_online_date else "Offline",
            UserStatus.RECENTLY: "Recently",
            UserStatus.LAST_WEEK: "Within a week",
            UserStatus.LAST_MONTH: "Within a month",
        }
        return status_map.get(user.status, "Long time ago")

    async def _format_user_info(self, user: User, is_full: bool, message: Message) -> tuple[str, str | None]:
        """Gathers and formats user information."""
        full_chat_info = await message._client.get_chat(user.id)
        safe_escape = lambda text: html.escape(str(text)) if text else ""

        info_lines = [f"<b>User Info for {user.mention}:</b>"]
        info_lines.extend([f"• <b>ID:</b> <code>{user.id}</code>"])
        if user.username: info_lines.append(f"• <b>Username:</b> @{user.username}")
        if user.dc_id: info_lines.append(f"• <b>DC ID:</b> {user.dc_id}")
        
        flags = []
        if user.is_bot: flags.append("Bot 🤖")
        if user.is_verified: flags.append("Verified ✅")
        if user.is_scam: flags.append("Scam ‼️")
        if user.is_premium: flags.append("Premium ✨")
        if flags: info_lines.append(f"• <b>Flags:</b> {', '.join(flags)}")
        
        info_lines.append(f"• <b>Last Seen:</b> {self._get_user_status(user)}")

        if is_full:
            if user.language_code: info_lines.append(f"• <b>Language:</b> {user.language_code}")
            if user.id != message.from_user.id:
                try:
                    common_chats = await message._client.get_common_chats(user.id)
                    info_lines.append(f"• <b>Common Groups:</b> {len(common_chats)}")
                except Exception: pass
                try:
                    await message._client.send_chat_action(user.id, enums.ChatAction.CANCEL)
                    info_lines.append("• <b>Blocked You:</b> No ✅")
                except UserIsBlocked:
                    info_lines.append("• <b>Blocked You:</b> Yes ⛔️")
                except Exception: pass
            
            if full_chat_info.bio: info_lines.append(f"• <b>Bio:</b> {safe_escape(full_chat_info.bio)}")
            
            photos_count = await message._client.get_chat_photos_count(user.id)
            if photos_count > 0: info_lines.append(f"• <b>Profile Photos:</b> {photos_count}")

        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            try:
                member = await message._client.get_chat_member(message.chat.id, user.id)
                if member:
                    info_lines.append("\n<b>Group Info:</b>")
                    status_map = {ChatMemberStatus.OWNER: "Owner", ChatMemberStatus.ADMINISTRATOR: "Administrator", ChatMemberStatus.MEMBER: "Member", ChatMemberStatus.RESTRICTED: "Restricted", ChatMemberStatus.LEFT: "Not in chat", ChatMemberStatus.BANNED: "Banned"}
                    status_str = status_map.get(member.status, "Unknown")
                    if member.custom_title: status_str += f" (Title: {safe_escape(member.custom_title)})"
                    info_lines.append(f"• <b>Status:</b> {status_str}")
                    if member.joined_date: info_lines.append(f"• <b>Joined:</b> {member.joined_date.strftime('%d %b %Y, %H:%M UTC')}")
            except Exception: pass
        
        info_lines.append(f"\n<b>Permalink:</b> <a href='tg://user?id={user.id}'>Click Here</a>")

        photo_id = full_chat_info.photo.big_file_id if full_chat_info.photo else None
        return "\n".join(info_lines), photo_id
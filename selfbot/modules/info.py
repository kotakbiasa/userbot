import datetime
import html
import re

from pyrogram import enums, filters
from pyrogram.enums import ChatType, UserStatus, ChatMemberStatus
from pyrogram.errors import RPCError, UserIsBlocked
from pyrogram.types import Message, User, LinkPreviewOptions

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(r"^info(.*)$", flags=re.DOTALL)


class Info(Module):
    name = "Info"
    cmds = "info {user_id|username}?"
    desc = {
        "user_id|username": "User ID or username of the target.",
        "?": "Optional. Reply to a message or get self info.",
        "-full": "Get detailed information.",
        "e.g.": "info @username",
        "e.g. (full)": "info -full @username",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Get user information."""
        await event.edit_text("<code>Fetching user information...</code>")
        now = datetime.datetime.now(datetime.UTC)

        match = pattern.match(event.text)
        input_str = match.group(1).strip()

        is_full_mode = "-full" in input_str.split()
        target_identifier = input_str.replace("-full", "").strip()

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

        if is_full:
            info_lines = ["<b>User Info:</b>"]
            info_lines.extend([f"• <b>ID:</b> <code>{user.id}</code>", f"• <b>First Name:</b> {safe_escape(user.first_name)}"])
            if user.last_name: info_lines.append(f"• <b>Last Name:</b> {safe_escape(user.last_name)}")
            if user.username: info_lines.append(f"• <b>Username:</b> @{user.username}")
            if user.dc_id: info_lines.append(f"• <b>DC ID:</b> {user.dc_id}")
            if user.language_code: info_lines.append(f"• <b>Language:</b> {user.language_code}")

            if user.id != message.from_user.id:
                try:
                    common_chats = await self.client.app.get_common_chats(user.id)
                    info_lines.append(f"• <b>Common Groups:</b> {len(common_chats)}")
                except Exception:
                    pass  # Ignore if unable to fetch common chats
                
                try:
                    await self.client.app.send_chat_action(user.id, enums.ChatAction.CANCEL)
                    info_lines.append("• <b>Blocked You:</b> No ✅")
                except UserIsBlocked:
                    info_lines.append("• <b>Blocked You:</b> Yes ⛔️")
                except Exception:
                    pass  # Ignore if unable to fetch common chats

            flags = []
            if user.is_bot: flags.append("Bot 🤖")
            if user.is_verified: flags.append("Verified ✅")
            if user.is_scam: flags.append("Scam ‼️")
            if user.is_premium: flags.append("Premium ✨")
            if flags: info_lines.append(f"• <b>Flags:</b> {', '.join(flags)}")
            
            # Get registration date from external API
            try:
                async with self.client.http as http_client:
                    reg_date_resp = await http_client.get(
                        f"https://yasirapi.eu.org/register_date?user_id={user.id}&tz=UTC"
                    )
                if reg_date_resp.status_code == 200 and (reg_date_data := reg_date_resp.json()).get("success"):
                    info_lines.append(f"• <b>Registration Date:</b> {reg_date_data.get('reg_date')} UTC")
            except Exception:
                pass  # Ignore if API fails, so it doesn't break the whole command

            info_lines.append(f"• <b>Last Seen:</b> {self._get_user_status(user)}")
            
            if full_chat_info.bio: info_lines.append(f"• <b>Bio:</b> {safe_escape(full_chat_info.bio)}")
            
            photos_count = await message._client.get_chat_photos_count(user.id)
            if photos_count > 0: info_lines.append(f"• <b>Profile Photos:</b> {photos_count}")

            if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                try:
                    member = await message._client.get_chat_member(message.chat.id, user.id)
                    if member:
                        info_lines.append("\n<b>Group Info:</b>")
                        group_details = []
                        status_map = {ChatMemberStatus.OWNER: "Owner", ChatMemberStatus.ADMINISTRATOR: "Administrator", ChatMemberStatus.MEMBER: "Member", ChatMemberStatus.RESTRICTED: "Restricted", ChatMemberStatus.LEFT: "Not in chat", ChatMemberStatus.BANNED: "Banned"}
                        status_str = status_map.get(member.status, "Unknown")
                        if member.custom_title: status_str += f" (Title: {safe_escape(member.custom_title)})"
                        group_details.append(f"• <b>Status:</b> {status_str}")
                        if member.joined_date: group_details.append(f"• <b>Joined:</b> {member.joined_date.strftime('%d %b %Y, %H:%M UTC')}")
                        if member.promoted_by: group_details.append(f"• <b>Promoted By:</b> {member.promoted_by.mention}")
                        if member.privileges:
                            perms = member.privileges
                            perm_list = [
                                ("– Manage Chat", perms.can_manage_chat), ("– Delete Messages", perms.can_delete_messages),
                                ("– Manage Video Chats", perms.can_manage_video_chats), ("– Restrict Members", perms.can_restrict_members),
                                ("– Change Info", perms.can_change_info), ("– Invite Users", perms.can_invite_users),
                                ("– Pin Messages", perms.can_pin_messages), ("– Post Stories", perms.can_post_stories),
                                ("– Edit Stories", perms.can_edit_stories), ("– Delete Stories", perms.can_delete_stories)
                            ]
                            granted_perms = [text for text, has_perm in perm_list if has_perm]
                            if granted_perms: group_details.append("• <b>Permissions:</b>\n" + "\n".join(granted_perms))
                        info_lines.append(f"<blockquote>{'<br>'.join(group_details)}</blockquote>")
                except Exception: pass
            
            info_lines.append(f"\n<b>Permalink:</b> <a href='tg://user?id={user.id}'>Click Here</a>")

        else:
            info_lines = ["<b>User info:</b>", f"• <b>ID:</b> <code>{user.id}</code>", f"• <b>First Name:</b> {safe_escape(user.first_name)}"]
            if user.last_name: info_lines.append(f"• <b>Last Name:</b> {safe_escape(user.last_name)}")
            if user.username: info_lines.append(f"• <b>Username:</b> @{user.username}")
            try:
                if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                    member = await message._client.get_chat_member(message.chat.id, user.id)
                    status_map = {ChatMemberStatus.OWNER: "Owner", ChatMemberStatus.ADMINISTRATOR: "Admin", ChatMemberStatus.MEMBER: "Member", ChatMemberStatus.RESTRICTED: "Restricted", ChatMemberStatus.LEFT: "Not in chat", ChatMemberStatus.BANNED: "Banned"}
                    if member.status in status_map:
                        status_str = status_map.get(member.status)
                        info_lines.append(f"• <b>Status:</b> {status_str}")
            except Exception: pass
            info_lines.append(f"\n<b>Permalink:</b> {user.mention('Click Here')}")

        photo_id = full_chat_info.photo.big_file_id if full_chat_info.photo else None
        return "\n".join(info_lines), photo_id
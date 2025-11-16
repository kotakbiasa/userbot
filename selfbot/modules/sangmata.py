import asyncio
import html
import re

from pyrogram import filters
from pyrogram.errors import YouBlockedUser
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils.conversation import Conversation

pattern = re.compile(r"^sg(?: (.+))?$")


class SangMata(Module):
    name = "SangMata"
    cmds = "sg {user_id|username} or <Reply>"
    desc = {
        "Info": "Tracks a user's name history using an external bot.",
        "e.g.": "sg @username",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_sg_command(self, event: Message) -> None:
        """Handles the .sg command to get user history via @SangMata_bot."""
        response_msg = await event.edit_text("<code>Processing please wait</code>")

        target_identifier = None
        match = pattern.match(event.text)
        if event.reply_to_message and event.reply_to_message.from_user:
            target_identifier = event.reply_to_message.from_user.id
        elif match and match.group(1):
            target_identifier = match.group(1).strip()

        if not target_identifier:
            await response_msg.edit_text(
                f"<b>Usage: </b><code>{self.cmds}</code>"
            )
            return

        try:
            user = await event._client.get_users(target_identifier)
            user_id = user.id
        except Exception as e:
            await response_msg.edit_text(f"<i>Error: {html.escape(str(e))}</i>")
            return

        bot_username = "@SangMata_beta_bot"
        try:
            async with Conversation(event._client, bot_username, timeout=15) as conv:
                await conv.send_message(str(user_id))
                response = await conv.get_response(timeout=10)
                if "you have used up your quota" in response.text:
                    await response_msg.edit(response.text.splitlines()[0])
                    return
                return await response_msg.edit(response.text)
        except YouBlockedUser:
            await response_msg.edit(f"<i>Please unblock @SangMata_beta_bot first.</i>")
        except asyncio.TimeoutError:
            await response_msg.edit("<i>No response from bot within the timeout period.</i>")
        except Exception as e:
            await response_msg.edit(f"<i>Error: {html.escape(str(e))}</i>")
import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.errors import YouBlockedUser
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec
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
        now = datetime.datetime.now(datetime.UTC)
        response_msg = await event.edit_text("<code>Processing...</code>")

        target_identifier = None
        match = pattern.match(event.text)
        if match and match.group(1):
            target_identifier = match.group(1).strip()
        elif event.reply_to_message and event.reply_to_message.from_user:
            target_identifier = event.reply_to_message.from_user.id

        if not target_identifier:
            await response_msg.edit_text(
                f"<b>Usage:</b> <code>{self.cmds}</code>"
            )
            return

        try:
            user = await event._client.get_users(target_identifier)
            user_id = user.id
        except Exception as e:
            await response_msg.edit_text(f"<b>Error:</b> <code>{html.escape(str(e))}</code>")
            return

        bot_username = "@SangMata_beta_bot"
        try:
            async with Conversation(event._client, bot_username, timeout=20) as conv:
                await conv.send_message(str(user_id))
                response = await conv.get_response()

                if "you have used up your quota" in response.text:
                    await response_msg.edit(response.text.splitlines()[0])
                    return

                await response_msg.edit(
                    f"{response.text}\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"
                )

        except YouBlockedUser:
            await response_msg.edit(f"<i>Please unblock {bot_username} first.</i>")
        except asyncio.TimeoutError:
            await response_msg.edit("<i>No response from bot within the timeout period.</i>")
        except Exception as e:
            await response_msg.edit(f"<b>Error:</b> <code>{html.escape(str(e))}</code>")
import asyncio
import html
import random
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.raw.functions.messages import DeleteHistory
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

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
        response_msg = await event.edit_text("<code>Processing...</code>")

        target_identifier = None
        match = pattern.match(event.text)
        if match.group(1):
            target_identifier = match.group(1).strip()
        elif event.reply_to_message and event.reply_to_message.from_user:
            target_identifier = event.reply_to_message.from_user.id

        if not target_identifier:
            await response_msg.edit_text(
                "<code>Please reply to a user or provide a user ID/username.</code>"
            )
            return

        try:
            user = await event._client.get_users(target_identifier)
            user_id = user.id
        except Exception as e:
            await response_msg.edit_text(f"<b>Error:</b> <code>{html.escape(str(e))}</code>")
            return

        bots = ["@Sangmata_bot", "@SangMata_beta_bot"]
        sangmata_bot = random.choice(bots)

        try:
            await event._client.unblock_user(sangmata_bot)
            txt = await event._client.send_message(sangmata_bot, str(user_id))
            await asyncio.sleep(5)  # Wait for the bot to process and reply

            history = event._client.get_chat_history(sangmata_bot, limit=1)
            async for bot_reply in history:
                if bot_reply.text:
                    await event.reply_text(bot_reply.text, quote=True)
                else:
                    await event.reply_text(f"❌ <b>{sangmata_bot} did not respond correctly.</b>", quote=True)

            # Clean up conversation with the bot
            await txt.delete()
            await bot_reply.delete()
            await response_msg.delete()

        except Exception as e:
            await response_msg.edit_text(f"<b>SangMata Error:</b> <code>{html.escape(str(e))}</code>")
import asyncio
import datetime
import html
import random
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.raw.functions.contacts import Unblock, Block
from pyrogram.raw.functions.messages import DeleteHistory, GetHistory
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

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

        bot_peer = await event._client.resolve_peer(sangmata_bot)

        try:
            # Send the user ID to the bot
            txt = await event._client.send_message(sangmata_bot, str(user_id))

            # Wait for the bot's response
            bot_reply = None
            for _ in range(10):  # Try for up to 10 seconds
                await asyncio.sleep(1)
                # We check the history for a message that is a reply to our request
                async for message in event._client.get_chat_history(sangmata_bot, limit=1):
                    # The bot should reply, but some bots just send a new message.
                    # We check if the message is from the bot and sent after our request.
                    if message.from_user.username == sangmata_bot.lstrip('@') and message.date > txt.date:
                        bot_reply = message
                        break
                if bot_reply:
                    break

            if bot_reply and bot_reply.text:
                # The bot's response might contain markdown, so we send it as is, with a timestamp.
                await response_msg.edit_text(f"{bot_reply.text}\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>")
            else:
                await response_msg.edit_text(f"❌ <b>{sangmata_bot} did not respond.</b>")

            # Clean up conversation with the bot
            # A short sleep to ensure messages are processed before deletion
            await asyncio.sleep(1)
            try:
                await event._client.invoke(DeleteHistory(peer=bot_peer, max_id=0, revoke=True))
            except RPCError:
                # If deletion fails, just block the bot to hide the chat
                await event._client.invoke(Block(id=bot_peer))

        except Exception as e:
            await response_msg.edit_text(f"<b>SangMata Error:</b> <code>{html.escape(str(e))}</code>")
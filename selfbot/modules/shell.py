import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, shell

# Pattern to match commands starting with $
pattern = re.compile(r"^\$(.+)$", flags=re.DOTALL)


class Shell(Module):
    name = "Shell"
    cmds = "$ {command}"
    desc = {
        "Info": "Executes a shell command.",
        "command": "The command to be executed.",
        "e.g.": "$ ls -l",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Handles shell command execution."""
        match = pattern.match(event.text)
        if not match:
            return

        command = match.group(1).strip()
        await event.edit_text(f"<code>$ {html.escape(command)}</code>")
        now = datetime.datetime.now(datetime.UTC)

        try:
            # Execute shell command with a 60-second timeout
            stdout, stderr = await asyncio.wait_for(shell(command), timeout=60.0)

            output = ""
            if stdout:
                output += f"<b>STDOUT:</b>\n<code>{html.escape(stdout)}</code>\n"
            if stderr:
                output += f"<b>STDERR:</b>\n<code>{html.escape(stderr)}</code>\n"

            if not output:
                output = "<code>Command executed with no output.</code>"

            # Add timestamp
            output += f"\n<b><blockquote>{fmtsec(now)}</blockquote></b>"

            await event.edit_text(output)

        except asyncio.TimeoutError:
            await event.edit_text("<b>Error:</b> <code>Command timed out after 60 seconds.</code>")
        except Exception as e:
            await event.edit_text(f"<b>Error:</b>\n<code>{html.escape(str(e))}</code>")
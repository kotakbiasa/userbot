import asyncio
import datetime
import html
import os
import re
from subprocess import PIPE, Popen, TimeoutExpired

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

pattern = re.compile(r"^(?:shell|sh)\s+(.+)$", flags=re.DOTALL)


class Shell(Module):
    name = "Shell"
    cmds = "sh|shell {command}"
    desc = {
        "Info": "Executes a shell command.",
        "command": "The command to be executed.",
        "e.g.": "sh ls -l",
    }

    @staticmethod
    def _run_command(command: str) -> tuple[str, str, int]:
        """Menjalankan perintah shell secara sinkron dan menangkap output."""
        cmd_obj = Popen(
            command,
            shell=True,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
        )
        try:
            stdout, stderr = cmd_obj.communicate(timeout=60)
        except TimeoutExpired:
            cmd_obj.kill()
            return None, "<b>Timeout expired (60 seconds)</b>", cmd_obj.returncode
        return stdout, stderr, cmd_obj.returncode

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Handles shell command execution."""
        match = pattern.match(event.text)
        if not match:
            await event.edit("<b>Specify the command in message text</b>")
            return

        command = match.group(1).strip()
        now = datetime.datetime.now(datetime.UTC)
        
        # Determine shell prompt character
        char = "#" if hasattr(os, 'getuid') and os.getuid() == 0 else "$"
        
        text = f"<b>{char}</b> <code>{html.escape(command)}</code>\n\n"
        await event.edit_text(text + "<b>Running...</b>")
        
        stdout, stderr, returncode = await asyncio.to_thread(self._run_command, command)

        if stdout:
            text += f"<b>Output:</b>\n<blockquote><code>{html.escape(stdout)}</code></blockquote>\n\n"
        if stderr:
            text += f"<b>Error:</b>\n<blockquote><code>{html.escape(stderr)}</code></blockquote>\n\n"
        
        text += f"<b>Return Code:</b> <code>{returncode}</code>\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"
        await event.edit_text(text)
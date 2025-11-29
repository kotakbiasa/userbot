import asyncio
import html
import os
import re
from subprocess import PIPE, Popen, TimeoutExpired
from time import perf_counter

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

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
    def _run_command(command: str) -> tuple[str, str, int, float]:
        """Runs a shell command synchronously and captures output."""
        start_time = perf_counter()
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
            return None, "<b>Timeout expired (60 seconds)</b>", cmd_obj.returncode, perf_counter() - start_time
        
        stop_time = perf_counter()
        elapsed = round(stop_time - start_time, 5)
        return stdout, stderr, cmd_obj.returncode, elapsed

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        """Handles shell command execution."""
        match = pattern.match(event.text)
        if not match:
            await event.edit("<b>Specify the command in message text</b>")
            return

        command = match.group(1).strip()
        
        # Determine shell prompt character
        char = "#" if hasattr(os, 'getuid') and os.getuid() == 0 else "$"
        
        text = f"<b>{char}</b> <code>{html.escape(command)}</code>\n\n"
        await event.edit_text(text + "<b>Running...</b>")

        stdout, stderr, returncode, elapsed = await asyncio.to_thread(self._run_command, command)

        if stdout:
            text += f"<b>Output:</b>\n<code>{html.escape(stdout)}</code>\n\n"
        if stderr:
            text += f"<b>Error:</b>\n<code>{html.escape(stderr)}</code>\n\n"
        
        text += f"<b>Completed in {elapsed} seconds with code {returncode}</b>"
        await event.edit_text(text)
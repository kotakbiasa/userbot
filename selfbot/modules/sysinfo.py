import asyncio
import datetime
import platform
import re
import shutil

import psutil
from pyrogram import __version__ as pyrogram_version
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(r"^sysinfo$")


def format_bytes(size: int) -> str:
    """Format bytes to a human-readable string."""
    power = 1024
    n = 0
    power_labels = {0: "", 1: "K", 2: "M", 3: "G", 4: "T"}
    while size > power and n < len(power_labels) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"


class Sysinfo(Module):
    name = "Sysinfo"
    cmds = "sysinfo"
    desc = "Displays system information."

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, priority=1)
    async def on_message_out(self, event: Message) -> None:
        """Displays system information."""
        await event.edit_text("<code>Gathering information...</code>")
        now = datetime.datetime.now(datetime.UTC)

        # Gather system info
        sys_info = await self.get_system_info()

        # Format the output
        await event.edit_text(fmtstr("System Info", sys_info, fmtsec(now)))

    def get_os_info(self) -> str:
        """Gets more descriptive OS information."""
        system = platform.system()
        if system == "Linux":
            try:
                # Use freedesktop_os_release for a better distro name (Python 3.10+)
                return platform.freedesktop_os_release().get(
                    "PRETTY_NAME", f"{system} {platform.release()}"
                )
            except (FileNotFoundError, AttributeError):
                return f"{system} {platform.release()}"  # Fallback
        elif system == "Darwin":
            return f"macOS {platform.mac_ver()[0]}"

        return f"{system} {platform.release()}"

    async def get_system_info(self) -> dict:
        """Gathers system information."""
        # CPU
        cpu_freq = psutil.cpu_freq()
        cpu_usage = psutil.cpu_percent(interval=1)

        cpu_info_str = f"{psutil.cpu_count(logical=False)} Cores, {psutil.cpu_count(logical=True)} Threads"
        if cpu_freq and cpu_freq.current:
            cpu_info_str += f" @ {cpu_freq.current:.2f} Mhz"
        cpu_info_str += f" ({cpu_usage}%)"
        # Memory
        mem = psutil.virtual_memory()

        # Disk
        disk = shutil.disk_usage("/")
        disk_percent = (disk.used / disk.total) * 100

        # Uptime
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot_time

        info = {
            "OS": self.get_os_info(),
            "Kernel": platform.release(),
            "CPU": cpu_info_str,
            "Architecture": platform.machine(),
        }

        try:
            load1, load5, load15 = psutil.getloadavg()
            info["Load Average"] = f"{load1:.2f}, {load5:.2f}, {load15:.2f}"
        except (AttributeError, NotImplementedError):
            # getloadavg() is not available on all OSes (e.g., Windows)
            pass

        info["RAM"] = f"{format_bytes(mem.used)} / {format_bytes(mem.total)} ({mem.percent}%)"
        swap = psutil.swap_memory()
        if swap.total > 0:
            info["Swap"] = f"{format_bytes(swap.used)} / {format_bytes(swap.total)} ({swap.percent}%)"
        info["Disk"] = f"{format_bytes(disk.used)} / {format_bytes(disk.total)} ({disk_percent:.2f}%)"
        info["Python"] = platform.python_version()
        info["Pyrogram"] = pyrogram_version
        info["Uptime"] = str(uptime).split(".")[0]

        return info
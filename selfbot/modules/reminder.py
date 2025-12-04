import asyncio
import datetime
import re
import time
import uuid

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec

remind_pattern = re.compile(r"^(s)?remind(me)?\s+(\S+)\s+(.+)$", re.DOTALL)
reminders_pattern = re.compile(r"^reminders$")


class Reminder(Module):
    name = "Reminder"
    cmds = [
        "remind {time} {text}",
        "remindme {time} {text}",
        "sremind {time} {text}",
        "sremindme {time} {text}",
        "reminders",
    ]
    desc = {
        "time": "Time format (HH:MM, YYYY-MM-DD_HH:MM, or relative N[smhdwy])",
        "text": "The reminder message to be sent.",
        "reminders": "List all active reminders.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_reminders = {}  # Stores active reminder tasks

    def parse_time(self, time_str: str):
        """
        Return tuple (delay_seconds, repeat_count, repeat_interval)
        """
        now = datetime.datetime.now()
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}

        # Recurring format N[smhdwy]xN
        match = re.match(r"^(\d+)([smhdwy])x(\d+)$", time_str)
        if match:
            num, unit, count = match.groups()
            interval = int(num) * units[unit]
            return interval, int(count), interval

        # Compound relative (e.g. 1h30m)
        matches = re.findall(r"(\d+)([smhdwy])", time_str)
        if matches:
            total = sum(int(num) * units[unit] for num, unit in matches)
            return total, 1, None

        # HH:MM
        if re.match(r"^\d{2}:\d{2}$", time_str):
            hour, minute = map(int, time_str.split(":"))
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target < now:
                target += datetime.timedelta(days=1)
            return (target - now).total_seconds(), 1, None

        # YYYY-MM-DD_HH:MM
        if re.match(r"^\d{4}-\d{2}-\d{2}_\d{2}:\d{2}$", time_str):
            date_part, hm = time_str.split("_")
            year, month, day = map(int, date_part.split("-"))
            hour, minute = map(int, hm.split(":"))
            target = datetime.datetime(year, month, day, hour, minute)
            return (target - now).total_seconds(), 1, None

        raise ValueError("Invalid time format")

    async def set_reminder(
        self, event: Message, time_str: str, text: str, silent: bool, self_only: bool
    ):
        try:
            delay, repeat_count, repeat_interval = self.parse_time(time_str)
        except ValueError as e:
            await event.edit_text(f"❌ Invalid time format: {e}")
            return

        reminder_id = str(uuid.uuid4())[:8]
        creation_time = time.time()
        target_time = creation_time + delay

        if silent:
            await event.delete()
        else:
            await event.edit_text(f"⏰ Reminder set for {time_str}")

        async def remind_task():
            try:
                for i in range(repeat_count):
                    # Calculate sleep duration based on target time to avoid drift
                    sleep_duration = (creation_time + delay + (i * (repeat_interval or 0))) - time.time()
                    if sleep_duration > 0:
                        await asyncio.sleep(sleep_duration)

                    target_chat = "me" if self_only else event.chat.id
                    await event.client.send_message(target_chat, f"🔔 Reminder: {text}")
            finally:
                # Remove from active list when done
                self.active_reminders.pop(reminder_id, None)

        task = asyncio.create_task(remind_task())
        self.active_reminders[reminder_id] = {
            "task": task,
            "target_time": target_time,
            "text": text,
            "repeat": f"{repeat_count} times, every {fmtsec(datetime.timedelta(seconds=repeat_interval), True)}" if repeat_interval else "once"
        }

    @listener.handler(filters.me & filters.command(["remind", "remindme", "sremind", "sremindme"], prefixes=""), 1)
    async def on_remind(self, event: Message):
        """Handles all reminder commands."""
        match = remind_pattern.match(event.text.strip())
        silent, self_only, time_str, text = match.groups()

        await self.set_reminder(event, time_str, text, silent=bool(silent), self_only=bool(self_only))

    @listener.handler(filters.me & filters.command("reminders", prefixes=""), 2)
    async def on_list_reminders(self, event: Message):
        """Lists all active reminders."""
        if not self.active_reminders: # Check if the dictionary is empty
            await event.edit_text("No active reminders.")
            return

        response = "<b>Active Reminders:</b>\n\n"
        for rid, r_info in self.active_reminders.items():
            remaining = r_info['target_time'] - time.time()
            remaining_str = fmtsec(datetime.timedelta(seconds=remaining), True) if remaining > 0 else "now"
            response += (f"• <b>ID:</b> <code>{rid}</code>\n"
                         f"  <b>In:</b> {remaining_str}\n"
                         f"  <b>Text:</b> {html.escape(r_info['text'][:30])}...\n")

        await event.edit_text(response)
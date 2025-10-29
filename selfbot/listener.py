from pyrogram import Client, filters
from pyrogram.enums import MessageServiceType
from pyrogram.types import Message
import functools
import functools
@functools.total_ordering
@functools.total_ordering
class Listener:
    def __init__(
        self, mod: type, func: callable, event: str, filters: callable, priority: int
    ) -> None:
        self.mod = mod
        self.func = func
        self.event = event
        self.filters = filters
        self.priority = priority

    def __lt__(self, other: "Listener") -> bool:
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Listener):
            return NotImplemented
        return self.priority == other.priority
        return self.priority < other.priority
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Listener):
            return NotImplemented
        return self.priority == other.priority


def handler(filters: callable, priority: int) -> callable:
    def wrapper(func: callable) -> callable:
        setattr(func, "filters", filters)
        setattr(func, "priority", priority)
        return func

    return wrapper


async def reply(_: filter, __: Client, event: Message) -> bool:
    return bool(
        event.reply_to_message
        and event.reply_to_message.service != MessageServiceType.FORUM_TOPIC_CREATED
    )


fltrep = filters.create(reply, "FltRep")

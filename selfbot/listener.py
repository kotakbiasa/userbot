import typing

from pyrogram import filters
from pyrogram.enums import MessageServiceType
from pyrogram.types import Message

if typing.TYPE_CHECKING:
    from selfbot.module import Module


class Listener:
    def __init__(
        self,
        mod: "Module",
        func: typing.Callable,
        event: str,
        filters: filters.Filter,
        priority: int,
    ) -> None:
        self.mod = mod
        self.func = func
        self.event = event
        self.filters = filters
        self.priority = priority

    def __lt__(self, other: "Listener") -> bool:
        return self.priority < other.priority


def handler(filters: filters.Filter, priority: int) -> typing.Callable:
    def wrapper(func: typing.Callable) -> typing.Callable:
        setattr(func, "filters", filters)
        setattr(func, "priority", priority)
        return func

    return wrapper


async def reply(_, __, event: Message) -> bool:
    return bool(
        event.reply_to_message
        and event.reply_to_message.service != MessageServiceType.FORUM_TOPIC_CREATED
    )


fltrep = filters.create(reply, "FltRep")

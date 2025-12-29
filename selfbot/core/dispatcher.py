import abc
import asyncio
import bisect
import contextlib
import typing

from pyrogram.errors import (
    FloodWait,
    MessageIdInvalid,
    MessageNotModified,
    QueryIdInvalid,
    SlowmodeWait,
)
from pyrogram.filters import Filter
from pyrogram.types import Update

from selfbot.listener import Listener
from selfbot.module import Module
from selfbot.utils import fmtmsg


class Dispatcher(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.listeners = {}
        super().__init__(**kwargs)

    async def dispatch(self, event: str, *args, **kwargs) -> None:
        for listener in self.listeners.get(event, []):
            try:
                if listener.filters and args and isinstance(args[0], Update):
                    if not await listener.filters(args[0]._client, args[0]):
                        continue

                await listener.func(*args, **kwargs)
            except (MessageIdInvalid, MessageNotModified, QueryIdInvalid):
                continue
            except (FloodWait, SlowmodeWait) as e:
                if e.value <= 30:
                    await asyncio.sleep(e.value)
                    with contextlib.suppress(Exception):
                        await listener.func(*args, **kwargs)
                else:
                    continue
            except Exception as e:
                tb = e.__traceback__
                while tb and tb.tb_next:
                    tb = tb.tb_next

                fn = getattr(tb.tb_frame.f_code, "co_filename", "-")
                ln = getattr(tb, "tb_lineno", "-")
                with contextlib.suppress(Exception):
                    await self.bot.send_message(
                        self.app.me.id,
                        fmtmsg(
                            e.__class__.__name__,
                            {
                                "Module": listener.mod.__class__.__name__,
                                "Event": f"{listener.event.replace('_', ' ').title()}\n",
                                "File": fn,
                                "Line": ln,
                            },
                            str(e),
                        ),
                    )

                listener.mod.logger.error(f"{e.__class__.__name__}: {e} at {fn}:{ln}")

    def registers(self, mod: Module) -> None:
        for event, func in self._funcs(mod, "on_"):
            done = False
            try:
                self.register(
                    mod,
                    func,
                    event,
                    filters=getattr(func, "filters", None),
                    priority=getattr(func, "priority", 99),
                )
                done = True
            finally:
                if not done:
                    self.unregisters(mod)

    def unregisters(self, mod: Module) -> None:
        slots = []
        for event, listeners in self.listeners.items():
            for listener in listeners:
                if listener.mod == mod:
                    slots.append(listener)

        for listener in slots:
            self.unregister(listener)

    def register(
        self,
        mod: Module,
        func: typing.Callable,
        event: str,
        *,
        filters: Filter | None = None,
        priority: int = 99,
    ) -> None:
        if event not in self.listeners:
            self.listeners[event] = []

        bisect.insort(
            self.listeners[event], Listener(mod, func, event, filters, priority)
        )
        self.updates()

    def unregister(self, listener: "Listener") -> None:
        self.listeners[listener.event].remove(listener)
        if not self.listeners[listener.event]:
            del self.listeners[listener.event]

        self.updates()

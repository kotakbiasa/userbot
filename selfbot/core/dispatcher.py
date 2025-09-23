import abc
import asyncio
import bisect
import contextlib
from typing import Any

from pyrogram.errors import FloodWait, MessageNotModified, QueryIdInvalid, SlowmodeWait

from selfbot.listener import Listener
from selfbot.module import Module


class Dispatcher(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.listeners: dict[str, list[Listener]] = {}

        super().__init__(**kwargs)

    async def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None:
        for listener in self.listeners.get(event, []):
            try:
                if listener.filters:
                    first_arg = args[0] if args else None
                    if not await listener.filters(first_arg._client, first_arg):
                        continue

                await listener.func(*args, **kwargs)

            except (MessageNotModified, QueryIdInvalid):
                continue

            except (FloodWait, SlowmodeWait) as e:
                if e.value <= 30:
                    await asyncio.sleep(e.value)
                    try:
                        await listener.func(*args, **kwargs)
                    except Exception as r:
                        self.logger.warning(f"Retry Failed: {r}")
                else:
                    raise

            except Exception as e:
                tb = e.__traceback__
                while tb and tb.tb_next:
                    tb = tb.tb_next

                fn = tb.tb_frame.f_code.co_filename if tb else "N/A"
                ln = tb.tb_lineno if tb else "N/A"
                with contextlib.suppress(Exception):
                    self.logger.error(f"{exc.__class__.__name__}: {e} at {fn}:{ln}")

    def registers(self, mod: "Module") -> None:
        for event, func in self._funcs(mod, "on_"):
            done = False
            try:
                self.register(
                    mod,
                    func,
                    event,
                    filters=getattr(func, "filters", None),
                    priority=getattr(func, "priority", 100),
                )
                done = True
            finally:
                if not done:
                    self.unregisters(mod)

    def unregisters(self, mod: "Module") -> None:
        slots = []
        for event, listeners in self.listeners.items():
            for listener in listeners:
                if listener.mod == mod:
                    slots.append(listener)

        for listener in slots:
            self.unregister(listener)

    def register(
        self, mod: type, func: callable, event: str, *, filters=None, priority=100
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

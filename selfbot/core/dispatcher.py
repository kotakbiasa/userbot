import abc
import asyncio
import bisect
import contextlib

from pyrogram.errors import FloodWait, MessageNotModified, SlowmodeWait

from selfbot.listener import Listener
from selfbot.module import Module


class Dispatcher(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.listeners = {}

        super().__init__(**kwargs)

    async def dispatch(self, event: str, *args, **kwargs) -> None:
        tasks = []

        for listener in self.listeners.get(event, []):
            if listener.filters:
                arg = args[0]
                if not await listener.filters(arg._client, arg):
                    continue

            task = self.loop.create_task(listener.func(*args, **kwargs))
            tasks.append((listener, task))

        if tasks:
            coros = await asyncio.gather(*(t[1] for t in tasks), return_exceptions=True)
            for listener, result in zip((t[0] for t in tasks), coros):
                if isinstance(result, (FloodWait, SlowmodeWait)):
                    await asyncio.sleep(result.value)
                    with contextlib.suppress(MessageNotModified):
                        await listener.func(*args, **kwargs)

    def registers(self, mod: "Module") -> None:
        for event, func in self.funcs(mod, "on_"):
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

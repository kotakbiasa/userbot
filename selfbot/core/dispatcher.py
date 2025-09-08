import abc
import bisect

from selfbot.listener import Listener
from selfbot.module import Module


class Dispatcher(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.listeners = {}

        super().__init__(**kwargs)

    async def dispatch(self, event: str, *args, **kwargs) -> None:
        for listener in self.listeners.get(event, []):
            if listener.filters:
                event = args[0]
                if not await listener.filters(event._client, event):
                    continue

            await listener.func(*args, **kwargs)

    def registers(self, mod: "Module") -> None:
        for event, func in mod_funcs(mod, "on_"):
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


def mod_funcs(mod: "Module", prefix: str) -> list:
    res = []

    for attr in dir(mod):
        if attr.startswith(prefix):
            func = getattr(mod, attr)

            if callable(func):
                res.append((attr[len(prefix) :], func))

    return res

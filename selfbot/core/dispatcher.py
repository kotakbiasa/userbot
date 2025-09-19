import abc
import asyncio
import bisect
import contextlib
import traceback
from typing import Any

from pyrogram.errors import FloodWait, MessageNotModified, SlowmodeWait

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

            except MessageNotModified:
                continue

            except (FloodWait, SlowmodeWait) as e:
                delay = max(int(getattr(e, "value", 0) or 0), 0)
                self._schedule_retry(listener, args, kwargs, delay)

            except Exception as exc:

                tb = traceback.extract_tb(exc.__traceback__)
                if tb:
                    file, line, _, _ = tb[-1]
                    msg = f"{exc.__class__.__name__}: {exc} at {file}:{line}"
                else:
                    msg = f"{exc.__class__.__name__}: {exc}"

                with contextlib.suppress(Exception):
                    self.logger.error(msg)

    def _schedule_retry(
        self,
        listener: "Listener",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        delay: int,
    ) -> None:
        asyncio.create_task(self._retry_once(listener, args, kwargs, delay))

    async def _retry_once(
        self,
        listener: "Listener",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        delay: int,
    ) -> None:
        if delay > 0:
            await asyncio.sleep(delay)

        try:
            await listener.func(*args, **kwargs)
        except MessageNotModified:
            return
        except (FloodWait, SlowmodeWait) as e:
            next_delay = max(int(getattr(e, "value", 0) or 0), 0)
            self._schedule_retry(listener, args, kwargs, next_delay)
        except Exception as exc:

            tb = traceback.extract_tb(exc.__traceback__)
            if tb:
                file, line, _, _ = tb[-1]
                msg = f"{exc.__class__.__name__}: {exc} at {file}:{line}"
            else:
                msg = f"{exc.__class__.__name__}: {exc}"

            with contextlib.suppress(Exception):
                self.logger.error(msg)

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

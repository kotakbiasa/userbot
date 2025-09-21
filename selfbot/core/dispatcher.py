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

            except MessageNotModified:
                continue

            except (FloodWait, SlowmodeWait) as e:
                d = max(int(getattr(e, "value", 0) or 0), 0)
                asyncio.create_task(self._retry(listener, args, kwargs, d, 1))

            except Exception as exc:
                tb = exc.__traceback__
                while tb and tb.tb_next:
                    tb = tb.tb_next

                f = tb.tb_frame.f_code.co_filename if tb else "?"
                ln = tb.tb_lineno if tb else "?"
                with contextlib.suppress(Exception):
                    self.logger.error(f"{exc.__class__.__name__}: {exc} at {f}:{ln}")

    async def _retry(self, listener, args, kwargs, delay, attempt):
        if delay > 0:
            await asyncio.sleep(delay + min(1.0, 0.1 * attempt))

        try:
            await listener.func(*args, **kwargs)
        except (MessageNotModified, QueryIdInvalid):
            return
        except (FloodWait, SlowmodeWait) as e:
            if attempt >= 3:
                return

            nd = max(int(getattr(e, "value", 0) or 0), 0)
            if nd <= 30:
                asyncio.create_task(
                    self._retry(listener, args, kwargs, nd, attempt + 1)
                )
        except Exception as exc:
            tb = exc.__traceback__
            while tb and tb.tb_next:
                tb = tb.tb_next

            f = tb.tb_frame.f_code.co_filename if tb else "?"
            ln = tb.tb_lineno if tb else "?"
            with contextlib.suppress(Exception):
                self.logger.error(f"{exc.__class__.__name__}: {exc} at {f}:{ln}")

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

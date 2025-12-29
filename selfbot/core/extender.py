import abc
import inspect

from selfbot.module import Module, ModuleExists
from selfbot.modules import modules


class Extender(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.modules = {}
        super().__init__(**kwargs)

    def loads(self) -> None:
        for module in modules:
            for attr in dir(module):
                obj = getattr(module, attr)
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, Module)
                    and obj is not Module
                ):
                    self.load(obj)

    def unloads(self) -> None:
        for key in tuple(self.modules):
            self.unload(self.modules[key])

    def load(self, obj: type) -> None:
        if obj.__name__ in self.modules:
            raise ModuleExists(obj)

        mod = obj(self)
        try:
            self.registers(mod)
        except Exception as e:
            self.unregisters(mod)
            self.logger.error(f"{e.__class__.__name__}: {e}")
        else:
            self.modules[mod.__class__.__name__] = mod
            self.logger.info(f"{mod.__class__.__name__} Loaded")

    def unload(self, mod: Module) -> None:
        try:
            self.unregisters(mod)
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
        else:
            self.logger.info(f"{mod.__class__.__name__} Unloaded")
        finally:
            del self.modules[mod.__class__.__name__]

    @staticmethod
    def _funcs(mod: Module, prefix: str) -> list:
        res = []
        for attr in dir(mod):
            if attr.startswith(prefix):
                func = getattr(mod, attr)
                if callable(func):
                    res.append((attr[len(prefix) :], func))

        return res

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selfbot.core import Selfbot


class Module:
    name = ""
    cmds = ""
    desc = None

    def __init__(self, client: "Selfbot") -> None:
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)


class ModuleError(Exception):
    pass


class ModuleExists(ModuleError):
    def __init__(self, old: "Module", new: "Module") -> None:
        self.old = old
        self.new = new
        super().__init__(f"'{self.old.name}' Exists")

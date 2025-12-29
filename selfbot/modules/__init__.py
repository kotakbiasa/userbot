import importlib
import pathlib
import pkgutil

modules = [
    importlib.import_module(f".{info.name}", __name__)
    for info in pkgutil.iter_modules([str(pathlib.Path(__file__).parent)])
]
if globals().get("reload", False):
    for module in modules:
        importlib.reload(module)
else:
    reload = True

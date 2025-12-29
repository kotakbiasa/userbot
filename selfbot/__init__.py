import pathlib
import tomllib


def version() -> str:
    path = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)

        return data.get("project", {}).get("version", "?")
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return "?"


__version__ = version()

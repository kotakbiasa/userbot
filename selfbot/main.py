import asyncio
import logging
import os

from dotenv import dotenv_values

try:
    import uvloop
except ImportError:
    loop = asyncio.new_event_loop()
else:
    loop = uvloop.new_event_loop()
finally:
    asyncio.set_event_loop(loop)

from .core import Selfbot

logging.basicConfig(
    format="%(asctime)s,%(msecs)03d [ %(levelname).1s ] %(name)s: %(message)s",
    datefmt="%b %-d | %-I:%M %p | %-S",
    level=logging.INFO,
)
for lib in ("pyrogram", "httpx"):
    logging.getLogger(lib).setLevel(logging.ERROR)


def config() -> dict:
    config = dotenv_values()
    if not config:
        config = {
            k: v
            for k, v in os.environ.items()
            if k
            in ("DATABASE_URL", "GEMINI_API_KEY", "GEMINI_MODEL", "STICKER_FILE_ID")
        }

    return config


def run() -> None:
    try:
        loop.run_until_complete(Selfbot.launch(config(), loop))
    except RuntimeError as e:
        logging.critical(f"{e.__class__.__name__}: {e}")
    finally:
        if loop and not loop.is_closed():
            loop.close()


if __name__ == "__main__":
    run()

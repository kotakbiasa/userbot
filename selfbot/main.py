import asyncio
import logging
import os

import aiorun
from dotenv import dotenv_values

from .core import Selfbot

logging.basicConfig(
    format="%(asctime)s,%(msecs)03d [ %(levelname).1s ] %(name)s: %(message)s",
    datefmt="%b %-d | %-I:%M %p | %-S",
    level=logging.INFO,
)
for lib in ["pyrogram", "httpx"]:
    logging.getLogger(lib).setLevel(logging.ERROR)


def config() -> dict:
    config = {k.lower(): v for k, v in (dotenv_values() or os.environ).items()}
    if not (config.get("app_session_string") or config.get("bot_session_string")):
        raise SystemExit("Missing app_string_session or bot_string_session")

    return config


def run() -> None:
    try:
        import uvloop
    except ImportError:
        pass
    else:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    aiorun.logger.disabled = True
    aiorun.run(Selfbot.launch(config(), loop=loop), loop=loop)

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
    config = dotenv_values()

    if not config:
        config = {k.lower(): v for k, v in os.environ.items()}

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


import logging
import typing

from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
)

from selfbot.utils import ikm

if typing.TYPE_CHECKING:
    from selfbot.core import Selfbot


class Module:
    name = ""
    cmds = ""
    desc = None

    def __init__(self, client: "Selfbot") -> None:
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)

    async def answer(
        self,
        event: InlineQuery,
        reply_markup: InlineKeyboardMarkup = None,
        message_text: str = "",
        **kwargs,
    ) -> None:
        if not reply_markup:
            reply_markup = ikm((">_", "user_id", event._client.me.id))

        if not message_text:
            message_text = "<code>...</code>"

        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["STICKER_FILE_ID"],
                    reply_markup=reply_markup,
                    input_message_content=InputTextMessageContent(message_text),
                )
            ],
            **kwargs,
        )


class ModuleError(Exception):
    pass


class ModuleExists(ModuleError):
    def __init__(self, obj: type) -> None:
        super().__init__(f"Module '{obj.__name__}' Exists")

import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import RPCError
from pyrogram.types import Message, Update
from pyrogram.utils import get_channel_id

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtbyte, fmtmsg, fmtsec, prog

pattern = re.compile(
    r"^dl\s?(?:(?:https?://)?t\.me/(c/)?"
    r"([a-zA-Z][a-zA-Z0-9_]{3,30}[a-zA-Z0-9]|[1-9]\d{9})/(s/)?"
    r"([1-9]\d{0,9})(?:\?single)?)?(?:\s-n\s(.+))?$"
)


class Download(Module):
    name = "Download Message Media"
    cmds = "<Reply>? dl {url}? (-n {name})?"
    desc = {
        "url": "Message or Story URL",
        "name": "String",
        "?": "Optional",
        "e.g.": "dl https://t.me/durov/s/1",
    }

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")
        update, (private, chat_id, story, update_id, file_name) = (
            None,
            (pattern.match(event.content).groups()),
        )
        if event.reply_to_message:
            if not event.reply_to_message.media:
                await event.edit_text(
                    f"<code>{html.escape('<MessageMediaType>')} None</code>"
                )
                return
            elif event.reply_to_message.media not in (
                MessageMediaType.ANIMATION,
                MessageMediaType.AUDIO,
                MessageMediaType.DOCUMENT,
                MessageMediaType.PHOTO,
                MessageMediaType.STICKER,
                MessageMediaType.STORY,
                MessageMediaType.VIDEO,
                MessageMediaType.VIDEO_NOTE,
                MessageMediaType.VOICE,
            ):
                await event.edit_text(
                    f"<code>Unsupported {html.escape(f'<{event.reply_to_message.media}>')}</code>"
                )
                return
            elif event.reply_to_message.media == MessageMediaType.STORY:
                update = await event._client.get_stories(
                    event.reply_to_message.story.chat.id,
                    event.reply_to_message.story.id,
                )
            else:
                update = event.reply_to_message
        else:
            if not chat_id:
                await event.edit_text(
                    f"<code>{html.escape('<Reply>')} or Give a Message or Story URL </code>"
                )
                return
            else:
                if story:
                    func = event._client.get_stories
                else:
                    func = event._client.get_messages
                    if private:
                        chat_id = get_channel_id(int(chat_id))

                now = datetime.datetime.now(datetime.UTC)
                try:
                    update = await func(chat_id, int(update_id))
                except RPCError as e:
                    await event.edit_text(
                        fmtmsg(
                            e.__class__.__name__,
                            e.MESSAGE.format(value=e.value),
                            fmtsec(now),
                        )
                    )
                    return

        await self.download(event, update, file_name or "")

    async def download(
        self, event: Message, update: Update, file_name: str = ""
    ) -> None:
        fut = asyncio.create_task(
            update.download(
                file_name=file_name, progress=prog, progress_args=(event, "download")
            ),
            name=f"{event.chat.id}/{event.id}",
        )
        now = datetime.datetime.now(datetime.UTC)
        try:
            res = await fut
        except (asyncio.CancelledError, Exception) as e:
            await event.edit_text(
                fmtmsg(
                    e.__class__.__name__,
                    (
                        e.MESSAGE.format(value=e.value)
                        if isinstance(e, RPCError)
                        else str(e)
                    ),
                    fmtsec(now),
                )
            )
        else:
            obj = getattr(update, update.media.value)
            await event.edit_text(
                fmtmsg(
                    "Media Downloaded",
                    {
                        "File Path": res,
                        "File Size": f"{fmtbyte(obj.file_size)}\n",
                        **(
                            {"MIME Type": f"{obj.mime_type}\n"}
                            if hasattr(obj, "mime_type")
                            else {}
                        ),
                        **({"Width": obj.width} if hasattr(obj, "width") else {}),
                        **({"Height": obj.height} if hasattr(obj, "height") else {}),
                        **(
                            {"Duration": fmtsec(obj.duration, human=True)}
                            if hasattr(obj, "duration")
                            else {}
                        ),
                    },
                    fmtsec(now),
                )
            )

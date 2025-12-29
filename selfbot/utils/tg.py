import struct

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from pyrogram.utils import (
    MIN_MONOFORUM_CHANNEL_ID,
    get_channel_id,
    unpack_inline_message_id,
)

from .fmt import fmtbar, fmtbyte, fmtmsg, fmtsec


def ids(inline_message_id: str) -> tuple:
    data = unpack_inline_message_id(inline_message_id)
    try:
        cid, mid = data.owner_id, data.id
    except AttributeError:
        cid, mid = struct.unpack(">ii", data.id.to_bytes(8, signed=True))

    if cid < 0 or cid >= MIN_MONOFORUM_CHANNEL_ID:
        cid = get_channel_id(abs(cid))

    return cid, mid


def ikm(rows: list | tuple) -> InlineKeyboardMarkup:
    if isinstance(rows, tuple):
        rows = [[rows]]

    if isinstance(rows, list) and isinstance(rows[0], tuple):
        rows = [rows]

    ikb = []
    for row in rows:
        line = []
        for i in row:
            kwargs, last = {"text": i[0]}, i[-1]
            if len(i) == 2:
                kwargs["callback_data"] = last
            elif len(i) == 3:
                kwargs[i[1]] = last
            else:
                raise ValueError

            line.append(InlineKeyboardButton(**kwargs))

        ikb.append(line)

    return InlineKeyboardMarkup(ikb)


async def prog(current: int, total: int, event: Update, title: str = "") -> None:
    time = event._client.loop.time()
    if not hasattr(event, "_start"):
        event._start, event._last = time, time
        return

    if time - event._last >= 2.5:
        delta = time - event._start
        speed = current / delta
        if isinstance(event, Message):
            edit = event.edit_text
        else:
            edit = event.edit_message_text

        await edit(
            fmtmsg(
                f"{title.title()} Progress".lstrip(),
                {
                    "Current": fmtbyte(current),
                    "Total": f"{fmtbyte(total)}\n",
                    "Speed": f"{fmtbyte(speed)}/s\n",
                    "Elapsed": fmtsec(delta, human=True),
                    "Estimated": fmtsec(
                        (total - current) / speed if speed > 0 else 0, human=True
                    ),
                },
                fmtbar(current, total),
            )
        )
        event._last = time
